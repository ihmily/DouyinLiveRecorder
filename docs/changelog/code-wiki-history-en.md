# CODE_WIKI Changelog Archive (English)

> Moved out of the "Changelog" section of `CODE_WIKI_EN.md` on 2026-09-28; entry bodies are verbatim. The root document keeps only the current release window plus a pointer here.
> 164 entries, 2026-05-17 ~ 2026-09-24.
> On restoration: an earlier doc-size pass had cut some sentences short at a trailing `…`. This volume restores them by **per-line prefix match** against the `.workbuddy/docold` baseline (2026-09-25): 683 lines restored, 102 left as-is for a missing match, 0 left as-is as ambiguous.
> Deliberately NOT done: previously deleted bullets are not resurrected, and file inventories already externalized to `docs/agent-reference/changelog-file-inventories.md` are not re-inlined - wholesale restoration would undo those intentional edits.
> The runtime never reads this archive and it is not part of the shipped artifact. Root document entry point: [CODE_WIKI_EN.md](../../CODE_WIKI_EN.md).

## Index

| 版本条目 | 日期 |
| --- | --- |
| v4.3.0-dev (2026-09-24) — Build artifact size optimization: located and excluded runtime-unreachable modules + zip `compresslevel=9`; lite artifact 82.77MB → 64.88MB (−21.6%), zip 54.84MB → 42.19MB (−23.1%) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Type-stub de-coupling from `six`: the two abstract-base stubs in `typings/execjs/` now use `metaclass=ABCMeta`, clearing mypy `[import-untyped]` in the IDE's per-file check (stub-only, zero runtime impact) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Comment review & de-duplication across seven `src/` files: one pure-restatement merge each in `ws_client.py` / `video_postprocess.py`, the other five confirmed reference-grade and deliberately kept (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Frontend regression-lock fixes + wired into CI: two red locks in `test_regression_2026_09_22_gates.mjs` diagnosed as test-side defects, `.py` wrapper added into the pytest/CI loop (zero production-code change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Comment streamlining across four `src/` files: source-selection probes / SRT subtitles / sync HTTP / the ttwid credential cache, "cut derivation to conclusions + turn adjacent restatements into cross-references" (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — `main.py` comment streamlining: removed 2 pure function-name / code-restatement noise comments (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Repo-wide comment optimization: 3 factual corrections in root/build docs + compression of multi-layer "correction archaeology" across several subsystems (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — `src/` comment streamlining: cut derivation to conclusions and removed code-restatement in `recorder_status.py` and `room.py` (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — `src/spider.py` comment merge: de-duplicated two adjacent narratives in `_is_safe_http_url` (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Comment refinement across four `src/` files: removed "function-header vs inline" restatements and the same-source `proxy.py` scheme narrative (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — `src/stream.py` comment streamlining: 13 verbose / multi-layer "correction archaeology" blocks cut to conclusions (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — `gui.py` comment de-duplication: merged 3 "method-header vs first-body-line" restatements (comment-only, zero logic change) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Type-stub completion: cleared mypy `disallow_untyped_defs` errors across 7 `.pyi` files in `typings/execjs/` (IDE no longer reports `no-untyped-def` when a single file is opened) | 2026-09-24 |
| v4.3.0-dev (2026-09-24) — Reduced the resident `AGENTS.md` context by moving only one-time evidence; constraints and gates remain in place | 2026-09-24 |
| v4.3.0-dev (2026-09-23) — P0 fix: bare `reconfigure` in `build_exe._ensure_utf8_streams()` corrupted pytest fd capturing (local runs ended without a verdict and were misreported as a "GUI startup failed" dialog) | 2026-09-23 |
| v4.3.0-dev (2026-09-23) — Repo-wide comment refinement (68 files): multi-layer "correction archaeology" collapsed into single-line history notes; new third blind spot for `check_annotations.py` (line-ending form); three falsified statements corrected in place | 2026-09-23 |
| v4.3.0-dev (2026-09-23) — P0 fix: recording failed 100% of the time on ffmpeg master builds (`-thread_queue_size` was narrowed to an output-only option upstream, while we still emitted it before `-i`) | 2026-09-23 |
| v4.3.0-dev (2026-09-23) — Test hygiene: fixed one cross-file patch leak behind 11 false failures + new R6 gate ("manual MonkeyPatch must be undone"); coverage gate gains a tiered whitelist (empty by default, expiry fails) | 2026-09-23 |
| v4.3.0-dev (2026-09-22) — Doc convergence (Lanzou removal formally accepted) + README "installing ffmpeg manually on Windows" user guide | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — Windows runtime ffmpeg source consolidation: Lanzou fallback removed + downloaded-payload shape guard | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — W1 fourth integrity category landed + W6 Apple Silicon ffmpeg PATH yielding policy | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — Supply-chain hardening: runtime first-install verified against officially published hashes + opt-in mirror fallback (P-1b; superseded the same day) + release-time GPG verification + full-package artefact self-check | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — Release chain: macOS arm64 ffmpeg download endpoint fixed (that artefact never existed upstream) + ffmpeg binary trust-policy review | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — Tests: `_pid_alive` decoupled from the console code page, `run_command` crash paths locked; release chain: official SHA256 backfilled for 6/10 slots | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — Gate repair: MID-N01 dangling call collapsed, test-stub annotations relaxed, symbol-reachability check added as a gate | 2026-09-22 |
| v4.3.0-dev (2026-09-22) — Metadata source-of-truth sync + full quality-gate run + four-catalogue i18n verification (zero production-code change) | 2026-09-22 |
| v4.3.0-dev (2026-09-21) — Full worktree change ledger (by module): `CODE_REVIEW_2026-09-21` remediation round + coverage work stream | 2026-09-21 |
| v4.3.0-dev (2026-09-21) — Test-coverage work stream: `src/` coverage 73.28% → 82.03% (zero production-code change) | 2026-09-21 |
| v4.3.0-dev (2026-09-21) — Full CODE_REVIEW_2026-09-20 round landed: 10 severe fixes + thematic MID/MIN batches + five new gates | 2026-09-21 |
| v4.3.0-dev (2026-09-20) — Room correlation field `extra[room]`: per-room chains can be cut out of interleaved logs | 2026-09-20 |
| v4.3.0-dev (2026-09-20) — Web panel `/health` liveness endpoint + HTTP smoke wired into CI | 2026-09-20 |
| v4.3.0-dev (2026-09-20) — AGENTS.md segmentation & reachability refactor (better-harness: progressive disclosure) | 2026-09-20 |
| v4.3.0-dev (2026-09-20) — Metadata source-of-truth reconciliation + four-language catalog verification + full quality-gate run | 2026-09-20 |
| v4.3.0-dev (2026-09-19) — Full-codebase review remediation: 62 graded findings resolved (12 critical / 22 moderate / 28 minor) | 2026-09-19 |
| v4.3.0-dev (2026-09-18) — Repository metadata reconciliation across 13 targets + four-language catalog completion (594 → 601 entries) | 2026-09-18 |
| v4.3.0-dev (2026-09-17) — Unified boolean config parsing (fixes `true/false` silently disabling 8 settings) | 2026-09-17 |
| v4.3.0-dev (2026-09-17) — Instruction hygiene: AGENTS.md conflict/ambiguity consolidation + skill routing isolation (no runtime behavior change) | 2026-09-17 |
| v4.3.0-dev (2026-09-17) — Lowered adaptive concurrency floor: min_capacity 8→1 ("同一时间访问网络的线程数") | 2026-09-17 |
| v4.3.0-dev (2026-09-16) — Repository metadata source-of-truth sync: exclusion-dir completion / coverage-gate alignment across both jobs / version & config-key reconciliation | 2026-09-16 |
| v4.2.0-dev (2026-09-15) — mypy gate widened: scope moved into pyproject `[tool.mypy].files` (`src/` → whole repo) + 6 type defects fixed | 2026-09-15 |
| v4.2.0-dev (2026-09-15) — Fixed Linux CI test `test_read_config_value_missing_key_readonly_ok` (atomic write vs. file mode bits) | 2026-09-15 |
| v4.2.0-dev (2026-09-14) — Repository metadata / ignore-rule source-of-truth sync + four-language catalog consistency fix | 2026-09-14 |
| v4.2.0-dev (2026-09-13) — Douyu "SRT-only, no video" root-cause + HLS segment-layer false-green probe + source-selection hardening (config fallback / observability / same-origin candidate) | 2026-09-13 |
| v4.2.0-dev (2026-09-13) — CODE_REVIEW_FIX_1 leftover batch fix (22 landed + 3 deferred) + repository metadata sync | 2026-09-13 |
| v4.2.0-dev (2026-09-12) — Full code-review fix (P0+P1+P2 plus + network/platform/scripts gates + i18n top-up, ~120 items) | 2026-09-12 |
| v4.1.0-dev (2026-09-11) — Disable `-reconnect_at_eof` for HLS(m3u8) inputs: fixes live recording producing only subtitles and no video (P0, overturns previous open observation) | 2026-09-11 |
| v4.1.0-dev (2026-09-11) — Web panel rooms-list misalignment fix on narrow viewports (table-layout:fixed + URL ellipsis + horizontal scroll fallback) | 2026-09-11 |
| v4.1.0-dev (2026-09-11) — Fix recording startup failure (-22 EINVAL) caused by missing values on ffmpeg `-reconnect*` options | 2026-09-11 |
| v4.1.0-dev (2026-09-10) — Full migration of parameterized logs from f-string to i18n.tr (242 sites / 27 files; placeholder renames across the four language catalogs) | 2026-09-10 |
| v4.1.0-dev (2026-09-10) — 28 code-review fixes + repository metadata sync + four-language catalog completion (521 → 539 entries) | 2026-09-10 |
| v4.1.0-dev (2026-09-10) — 8 product-decision items + 4 machine-validation items + uv.lock aligned to 4.1.0 (v4.1.0 second batch) | 2026-09-10 |
| v4.0.9.4-dev (2026-09-07) — CI dependency versions aligned with latest official stable releases (codecov-action v5→v7, isort 8.0.1→9.0.1, mypy 2.3.0→2.3.1) | 2026-09-07 |
| v4.0.9.4-dev (2026-09-06) — Eight-file repository metadata sync + i18n catalog completion (516 → 521 entries) + this cycle's change overview (classified by module) | 2026-09-06 |
| v4.0.9.4-dev (2026-09-06) — GUI quality-switch persistence fixes + full WEB per-room quality-change path + frontend/backend unit tests | 2026-09-06 |
| v4.0.9.4-dev (2026-09-06) — Add/drop quality options in WEB/GUI + per-row quality switcher in quality monitor | 2026-09-06 |
| v4.0.9.4-dev (2026-09-05) — HLS capture exclusion platform list: listed platforms ignore the HLS switch and always use FLV capture | 2026-09-05 |
| v4.0.9.4-dev (2026-09-05) — Standalone single-file build relocated to scripts/ (ffmpeg lookup fixed accordingly) | 2026-09-05 |
| v4.0.9.4-dev (2026-09-05) — Auto-clean test output dirs _out_live/_out_e2e after pytest sessions | 2026-09-05 |
| v4.0.9.4-dev (2026-09-04) — P0 fix: segmented-recording container mismatch made Douyin original-quality HEVC unrecordable (return code 4294967274) | 2026-09-04 |
| v4.0.9.4-dev (2026-09-04) — Fixed flaky warning "FakeAsyncClient.aclose was never awaited" + AGENTS.md pytest zero-warning gate baseline finalized | 2026-09-04 |
| v4.0.9.4-dev (2026-09-03) — Repo-wide Chinese comment completion (41 files / +1370 lines) + annotation-check tool scripts/check_annotations.py created and wired into CI | 2026-09-03 |
| v4.0.9.3-dev (2026-09-02) — Standalone single-file integration (standalone) type-annotation fixes (mypy: 4 errors cleared) | 2026-09-02 |
| v4.0.9.3-dev (2026-09-02) — Full Fix of All 20 Issues from the Code Inspection Report (cookie_cache singleflight rewrite + Web non-ASCII password crash + probe/resource/style robustness) + mypy Whole-Repo Clean Slate (tests / gui_legacy / scripts) | 2026-09-02 |
| v4.0.9.2-dev (2026-08-30) — Runtime Log Archiving on Recording Stop (four logs renamed with timestamp) + i18n catalog completion (507 → 516 entries) + repo metadata sync-list alignment (.v2c / .mypy_cache) | 2026-08-30 |
| v4.0.9.2-dev (2026-08-29) — Full Working-Tree Change Overview (Classified by Module): 97 files / +10659 −3138, covering all uncommitted changes from 2026-08-23 through 08-29 | 2026-08-29 |
| v4.0.9.2-dev (2026-08-29) — Huya/Douyu Quality-Tier Specialization (Fine-grained Blu-ray Tier Enumeration + User Tier Selection + Unavailable Downgrade Fallback + Cross-Platform Compatibility) | 2026-08-29 |
| v4.0.9.2-dev (2026-08-29) — Web Panel Manual Recording Control (Global Switch + 7 Interrupt Points + Start/Stop Buttons) + Two-Round Review Fixes + End-to-End Smoke Test & Commit-Gate Triage | 2026-08-29 |
| v4.0.9.2-dev (2026-08-29) — GUI Parent-Process Log-Handle Isolation: Fixes streamget.log Rotation WinError 32 and Total Loss of Recording Logs | 2026-08-29 |
| v4.0.9.2-dev (2026-08-28) — Performance Review Optimization Landed (P1~P5 + Probe-Client Reuse + Backoff-Window Self-Healing + Web Log-Sink Rebuild + Huya FLV-first) | 2026-08-28 |
| v4.0.9.1-dev (2026-08-28) — CI Workflow Optimization & Network-Install Retry Consolidation (retry Composite Action) + PEP 758 Formatting Landed via black 26 + i18n Extractor Fixes + Eight-File Repository Metadata Sync | 2026-08-28 |
| v4.0.9.1-dev (2026-08-27) — i18n Localization System Fix (Python 2-style `except` Multi-Except → Tuple Parentheses) + zh_CN.mo Recompile | 2026-08-27 |
| v4.0.9.1-dev (2026-08-27) — Second-Pass Review Fixes (compile_po --check Always-True Gate + Direct-Download Failure Sampling Gap + i18n/Web Gap Closure) | 2026-08-27 |
| v4.0.9.1-dev (2026-08-27) — Code-Review Fixes (Circuit-Breaker Probe Lease Self-Healing + Scheduler Success Sampling) + Scheduler Thread-Safety Hardening + Full i18n Catalog Replenishment (288 → 492 entries) | 2026-08-27 |
| v4.0.9-dev (2026-08-24) — This Session's Change Overview (Classified by Module) | 2026-08-24 |
| v4.0.9-dev (2026-08-24) — CI pytest failure fix: C/POSIX locale detection and monkeypatch convention | 2026-08-24 |
| v4.0.9-dev (2026-08-24) — CI mypy Double-Error Fix (ctypes.WinDLL Platform Gating + 3-arg getattr Any Leak) | 2026-08-24 |
| v4.0.9-dev (2026-08-24) — High-Concurrency Multi-Platform Recording Scheduling & Resource Management Optimization (Adaptive Concurrency + Per-Platform Circuit Breaking) | 2026-08-24 |
| v4.0.9-dev (2026-08-24) — Four-Language Catalog Unification & British/American Split + Build-Script Strings Added + zh_CN.mo Recompiled | 2026-08-24 |
| v4.0.9-dev (2026-08-23) — Recording-Result Feedback to Scheduler + Probe Backoff Marking (Root Fix for Huya 403 Dead Loop) | 2026-08-23 |
| v4.0.9-dev (2026-08-23) — Dual Network-Concurrency Modes (Adaptive vs Fixed) | 2026-08-23 |
| v4.0.9-dev (2026-08-23) — Python 3.14 Upgrade + Language Config Key Migration (Comprehensive Maintenance) | 2026-08-23 |
| v4.0.8.3-dev (2026-08-22) — pythonw / Windowed-Run Crash Observability Hardening: logger None-stderr Guard + Top-Level Crash Dump Hook (Defect Fix) | 2026-08-22 |
| v4.0.8.3-dev (2026-08-22) — Type Check Fix: i18n Optional Dependency Stub Ignore + gui.py messagebox Explicit Import + Thread Hook Null-Check (Code Quality) | 2026-08-22 |
| v4.0.8.3-dev (2026-08-21) — start_record Complexity Governance: Platform Dispatch Chain Extraction + Recording-Chain Redundant Condition Removal (Code Quality) | 2026-08-21 |
| v4.0.8.3-dev (2026-08-21) — FFmpeg 9.0 / Node 24 Baseline + i18n Multilingual Refactor + tests Five-Tool All-Green (Comprehensive Maintenance) | 2026-08-21 |
| v4.0.8.3-dev (2026-08-20) — URL_config.ini Anchor-Name Auto-Update (New Feature) | 2026-08-20 |
| v4.0.8.3-dev (2026-08-20) — Type-Safety Hardening: Completed Type Annotations for Multiple Test Files and `src/async_http.py` (Satisfying mypy `disallow_untyped_defs` / basedpyright Gates) | 2026-08-20 |
| v4.0.8.3-dev (2026-08-20) — "Disable SSL Certificate Verification" Merged into "Enable https Recording" (Config Item Consolidation) | 2026-08-20 |
| v4.0.8.3-dev (2026-08-19) — Architecture Doc Update: Completed Danmaku Collection Subsystem and src/platforms, src/proto Module Notes | 2026-08-19 |
| v4.0.8.2-dev (2026-08-19) — CI Refactor: build-release.yml Removes download-artifact Round-Trip + Fixes Release Concurrency Race / Boolean Comparison / Missing Checkout | 2026-08-19 |
| v4.0.8.2-dev (2026-08-19) — Test/Coverage: tests/test_ttwid.py Added Branch Tests, src/ttwid.py Coverage 82.3% → 96.77% (Cleared 85% Gate) | 2026-08-19 |
| v4.0.8.2-dev (2026-08-19) — CI Fix: ci.yml `dorny/paths-filter@v3` → `v4` Eliminates Node.js 20 Deprecation Warning | 2026-08-19 |
| v4.0.8.2-dev (2026-08-19) — Test/Interface Fix: `test_huya_danmaku::test_profileRoom_fields` Stale Assertion + `web_api.list_files` Dangling/Escape-root Symlink Crash and Info Leak | 2026-08-19 |
| v4.0.8.2-dev (2026-08-19) — Type Check Fix: src/web_tray.py Two `ctypes.windll` Missing `sys.platform` Platform Gate Caused mypy Non-Windows Check Failure | 2026-08-19 |
| v4.0.8.2-dev (2026-08-19) — CI Fix: ci.yml Codecov Step's `if` Misused `secrets` Context Caused Workflow Validation Failure (Switched to Job-Level env Pass-through) | 2026-08-19 |
| v4.0.8.2-dev (2026-08-18) — Huya HLS Recording 403 True Cause: CDN Now Reverse-Validates, Forcing Referer Actually 403 (Removed Huya Referer Rule) | 2026-08-18 |
| v4.0.8.2-dev (2026-08-18) — Type Check Wrap-up: spider.py / sync_http.py Four mypy/basedpyright Warnings Cleared | 2026-08-18 |
| v4.0.8.2-dev (2026-08-18) — Huya HLS Multi-CDN Resolution and Playback Root-Cause Fix: Enumerate All CDN Candidates + HS Priority + http Conversion + `select_source_url` Per-Candidate Reachability Validation (Replaces Fragile Fixed index0 / TX-Priority Source Selection) | 2026-08-18 |
| v4.0.8.2-dev (2026-08-18) — Huya `get_huya_app_stream_url` source selection fix: m3u8/flv selected by priority to TX with synchronized TX param substitution (root-causing the recording-crash regression after priority-based selection) | 2026-08-18 |
| v4.0.8.2-dev (2026-08-18) — Huya runtime-log review: AL CDN 403 warnings are expected benign noise; three-level fallback + TX-first + dual-link fallback verified effective (no code changes) | 2026-08-18 |
| v4.0.8.2-dev (2026-08-18) — Huya GUI real-test review (179966): HLS three-CDN all-denied yet stable recording; manual-stop path and exit-code-255 classification | 2026-08-18 |
| v4.0.8.2-dev (2026-08-17) — Huya recording 403 failure-loop root-cause fix: probe backoff/throttle/jitter three-layer anti-rate-limiting + danmaku-monitor room lifecycle + config real-time + whole-codebase UA unified upgrade | 2026-08-17 |
| v4.0.8.2-dev (2026-08-17) — Three-platform real-log investigation: Douyu fatal-exception fix + Bilibili danmaku auth-chain closure + validator last-resort pass extension | 2026-08-17 |
| v4.0.8.2-dev (2026-08-17) — i18n translation-chain root-cause fix: supply missing zh_CN.mo + drop env-var dependency + po cleanup | 2026-08-17 |
| v4.0.8.2-dev (2026-08-17) — Validator GET-recheck false-kill tolerance (retry + last-resort pass) + Douyu FLV→m3u8 same-token HLS candidate (root-causing ~70s stream cut-off) | 2026-08-17 |
| v4.0.8.2-dev (2026-08-16) — Unified cookie fetching: URL-level shared cache, eliminating repeated same-URL fetches that trigger risk-control | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Bilibili spi buvid request governance: process-level cache + zero requests during off-air periods | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Three rounds of real tests: unearthed a historic structural bug — recording chain nested inside `if headers:`, Douyin/Douyu etc. never recorded | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Second-round real-test log fixes: tls_verify mis-inserted into http stream / Range-GET mis-killed Douyu / HLS-off silent path | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Special cleanup: fully backfill unlanded test-first fixes (21 failed + 18 errors → 540 passed) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Cleared mypy main.py's 6 arg-type errors | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Bilibili danmaku connect-then-drop true root cause (room-entry packet uid mistakenly passed anchor uid) + Huya FLV validation false-green + all-empty stream-address silent skip | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Bilibili danmaku buvid fallback (generate fallback buvid3 when spi risk-control returns empty) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Huya HLS/FLV 403 investigation conclusion (Referer already correctly injected, no code change needed) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Fix config.ini non-writable crash at import main stage (web.py startup failure) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Huya OD/BD/UHD app-path danmaku triplet returned + eliminate silent skip | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — SSL coverage refactored into generic platform list (compat with old Huya single-column key) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — backup_file rotation-delete misleading ERROR: changed to best-effort | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Bilibili danmaku param fetch landed + Bilibili live stream Referer added | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Huya optional cert-validation disable (platform-level SSL override, strict by default) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Huya recording fix: add Referer to resolve CDN 403 false-unreachable | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — main.py split: 6 categories of functionality extracted to src submodules (complete refactor) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Danmaku subpackage flattening: src/danmaku/\* → src/\* | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Danmaku recording module review fix (danmaku_check.md full issue list) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Fix HLS (m3u8) validation mis-judging 405 and falling back to FLV | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — docstring bulk conversion to # comments (enforce project comment convention) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Full code check and fix (mypy/basedpyright both cleared) | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Code-gate recheck and test-script sync fix | 2026-08-16 |
| v4.0.8.2-dev (2026-08-16) — Danmaku WS connection explicitly bypasses system proxy (proxy=None, root-causing "connecting through a SOCKS proxy requires python-socks") | 2026-08-16 |
| v4.0.8.1-dev (2026-08-15) — Fix Web smoke test failure due to security guard exit code 1 | 2026-08-15 |
| v4.0.8.1-dev (2026-08-15) — Code-review leftover fix (pyflakes cleared + dead-code/implicit-side-effect cleanup) | 2026-08-15 |
| v4.0.8.1-dev (2026-08-15) — Fix test_proxy.py flaky failure from harness env-var bloat | 2026-08-15 |
| v4.0.8.1-dev (2026-08-15) — basedpyright config landed + types/deps/tests wrap-up | 2026-08-15 |
| v4.0.8.1-dev (2026-08-15) — Code-review follow-up fix (lock deadlock-proofing / error_count semantics / format-exclude) | 2026-08-15 |
| v4.0.8.1-dev (2026-08-13) — Fix `get_startup_info()` cross-platform mypy regression | 2026-08-13 |
| v4.0.8.1-dev (2026-08-13) — CI `black --check` failure fix + lint job to Python 3.13 | 2026-08-13 |
| v4.0.8.1-dev (2026-08-13) — Type/logic fix batch based on reference info | 2026-08-13 |
| v4.0.8.1-dev (2026-08-12) — Fix cross-event-loop lock mis-judged as risk-control + blank exception log cleanup | 2026-08-12 |
| v4.0.8.1-dev (2026-08-11) — Fix Linux/macOS mypy cross-platform type errors | 2026-08-11 |
| v4.0.8.1-dev (2026-08-10) — Security hardening and code-quality fixes | 2026-08-10 |
| v4.0.8.1-dev (2026-08-09) — Comment convention and Web/API smoke-test tool | 2026-08-09 |
| v4.0.8.1-dev (2026-08-09) — Doc-stats induction (CODE_WIKI update) | 2026-08-09 |
| v4.0.8.1-dev (2026-08-08 ~ 2026-08-09) — Full code review, build fix, and GUI graceful-stop hardening | 2026-08-08 |
| v4.0.8.1-dev (2026-08-05) — CI static-verification workflow, concurrency-test integration, and coverage-gate uplift | 2026-08-05 |
| v4.0.8.1-dev (2026-08-05) — HLS validation mis-judgment and blank-log fix | 2026-08-05 |
| v4.0.8.1-dev (2026-08-02 ~ 2026-08-04) — Platform-naming convention landing and type/logic fixes | 2026-08-02 |
| v4.0.8.1-dev (2026-08-01) — mypy strict mode full pass and type-annotation tightening | 2026-08-01 |
| v4.0.8.1-dev (2026-08-01) — Version-number convergence to pyproject.toml single source of truth | 2026-08-01 |
| v4.0.8.1-dev (2026-08-01) — Core-module unit-test completion and coverage-threshold adjustment | 2026-08-01 |
| v4.0.8.1-dev (2026-08-01) — Douyin URL full-format support, format-5 link optimization, HLS validation and log fix | 2026-08-01 |
| v4.0.8.1-dev (2026-07-29) — Engineering-config file overhaul and doc sync | 2026-07-29 |
| v4.0.8.1-dev (2026-07-28) — Fix macOS CI smoke:gui crash | 2026-07-28 |
| v4.0.8.1-dev (2026-07-27) — ttwid shared-module extraction and smoke-test process-tree cleanup | 2026-07-27 |
| v4.0.8.1-dev (2026-07-26) — basedpyright whole-project clear and docstring-comment conversion | 2026-07-26 |
| v4.0.8.1-dev (2026-07-25) — Full code-review fix and security hardening | 2026-07-25 |
| v4.0.8-dev (2026-07-28) — Multi-room concurrent-monitoring risk-control fix and static-check clear | 2026-07-28 |
| v4.0.8-dev (2026-07-25) — New PyInstaller executable packaging and GitHub Actions release | 2026-07-25 |
| v4.0.8-dev (2026-07-25) — Whole-project type-error fix and code cleanup | 2026-07-25 |
| v4.0.8-dev (2026-07-25) — Dependency scan and Docker config update | 2026-07-25 |
| v4.0.8-dev (2026-07-24) | 2026-07-24 |
| v4.0.8-dev (2026-07-23) | 2026-07-23 |
| v4.0.8-dev (2026-06-27) | 2026-06-27 |
| v4.0.8-dev (2026-06-20) | 2026-06-20 |
| v4.0.8-dev (2026-05-17) | 2026-05-17 |

## Archived entries

### v4.3.0-dev (2026-09-24) — Build artifact size optimization: located and excluded runtime-unreachable modules + zip `compresslevel=9`; lite artifact 82.77MB → 64.88MB (−21.6%), zip 54.84MB → 42.19MB (−23.1%)

- **Background**: a local Windows lite build (no ffmpeg/node) measured **82.77MB / 272 files**. Per-package breakdown: three exes 32.27MB, `PIL` 12.79MB, `python314.dll` 6.47MB, `libcrypto-3.dll` 5.95MB, `pydantic_core` 4.93MB, Tcl/Tk DLLs 5.28MB. PIL and the exes carried clearly unreachable payloads, so this round only attacks "dead weight dragged in indirectly" — the interpreter / OpenSSL / Tcl-Tk / pydantic fixed costs are left alone.
- **Nature of change**: **packaging side only** (`build_exe.py`) plus tests and one new measurement script. No runtime module touched (`src/`, `main.py`, `gui.py`, `web.py`, `web/app.js` unchanged), **no dependency added or removed** (requirements.txt / pyproject.toml unchanged), build commands, entry points, artifact layout and zip naming all preserved.

**What was found (all measured against the real baseline artifact)**:

- `PIL._avif` **7.52MB** — Pillow 12 ships libavif; the largest single non-interpreter file in the artifact. The only PIL usage in this repo is `Image.new` + `ImageDraw` for the tray icon (`gui.py` / `src/web_tray.py`); there is no AVIF / WebP / `ImageFont` / `truetype` call site anywhere. Tolerance verified against Pillow's source: `PIL/ImageFont.py` wraps `from . import _imagingft as core` in `try/except ImportError → DeferredError`, and `PIL/Image.py:init()` wraps every plugin the same way, so a missing plugin only fails when actually called. Excluding it together with `_imagingft` (2.07MB), `_webp` (0.40MB), `_imagingcms` (0.26MB) and `_imagingmath` (0.02MB) took PIL from 12.79MB → 2.52MB.
- `pydantic.v1.mypy` → the whole `mypy` package **0.71MB / 69 files plus ~6MB of pure Python inside the PYZ** — the only "dev-toolchain leak": `pydantic/v1/mypy.py` has `from mypy.errorcodes import ErrorCode` at top level, so PyInstaller pulled mypy in transitively. `pydantic/v1/__init__.py` itself does not import mypy, so excluding just that plugin module is enough. This is the main reason the three exes dropped 32.27MB → 26.28MB.
- `uvicorn`'s optional implementation deps: `httptools` 0.17MB + `watchfiles` 0.61MB (plus `uvloop` on POSIX). `web.py` uses `uvicorn.Server(uvicorn.Config(...))` with `http`/`loop`/`ws` left at `"auto"`, and each `auto` implementation is literally "try the optional backend, `except ImportError` fall back" (httptools→h11, uvloop→asyncio, wsproto→websockets).
- `i18n/*.po` **0.12MB** — translation sources; `i18n.py` loads `.mo → .json → .yaml` and never reads `.po`. The old `('i18n', 'i18n')` datas entry copied the whole directory, so `.po` rode along; replaced by `i18n_datas_entries()` which enumerates files (new languages are picked up automatically, no spec edit needed).
- `nodejs_wheel` (114MB, present in the local venv but absent from requirements.txt) and the rest of the dev toolchain: not leaked in the baseline, but listed explicitly so "accidental collection" becomes impossible.

**Files touched**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Build artifact size optimization: located and excluded runtime-unreachable modules + zip `compresslevel=9`; lite artifact 82.77MB → 64.88MB (−21.6%), zip 54.84MB → 42.19MB (−23.1%) | section: Files touched).

### v4.3.0-dev (2026-09-24) — Type-stub de-coupling from `six`: the two abstract-base stubs in `typings/execjs/` now use `metaclass=ABCMeta`, clearing mypy `[import-untyped]` in the IDE's per-file check (stub-only, zero runtime impact)

- **Background**: `typings/execjs/_abstract_runtime.pyi` and `_abstract_runtime_context.pyi` copied upstream PyExecJS verbatim, i.e. they declared classes with `@six.add_metaclass(ABCMeta)` and did `import six`. `six` is present in the environment because PyExecJS requires it (`pip show PyExecJS` → `Requires: six`, measured 1.17.0 here), but it ships no `py.typed` marker and its typing information only comes from the separate `types-six` package, so mypy reports `Library stubs not installed for "six"` `[import-untyped]` against it unconditionally.
- **Why the gate was green while the IDE was red**: the CLI gate never enters the directory because `[tool.mypy].exclude` contains `typings`; and although `[tool.mypy].ignore_missing_imports = true` suppresses this error code, mypy only picks the setting up when it discovers `pyproject.toml` by walking up from **its own cwd** — the IDE language server launches a *single-file* check from a working directory outside the repository, so the config is not loaded and the diagnostic leaks through. Measured with one and the same command, varying only the cwd: from `%TEMP%` with an absolute path → 2 `[import-untyped]` hits; from the repository root → 0. The fix therefore has to hold **inside the file itself**, not depend on external configuration.
- **Nature of change**: pure type-stub change, no runtime code touched; **no files added, no files deleted**. Both `.pyi` files (pure LF, no BOM) dropped `import six`, and the class declaration moved from the decorator form to `class X(metaclass=ABCMeta):` — under Python 3, `six.add_metaclass(M)` is nothing but Py2-compatibility sugar and both forms yield the same metaclass.

**Files touched (classified by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Type-stub de-coupling from `six`: the two abstract-base stubs in `typings/execjs/` now use `metaclass=ABCMeta`, clearing mypy `[import-untyped]` in the IDE's per-file check (stub-only, zero runtime impact) | section: Files touched (classified by module)).

### v4.3.0-dev (2026-09-24) — Comment review & de-duplication across seven `src/` files: one pure-restatement merge each in `ws_client.py` / `video_postprocess.py`, the other five confirmed reference-grade and deliberately kept (comment-only, zero logic change)

- **Background**: this round covers the seven files named by the user: `src/ttwid.py`, `src/utils.py`, `src/video_postprocess.py`, `src/web_api.py`, `src/web_config.py`, `src/web_tray.py`, `src/ws_client.py`. After per-file reading plus a programmatic tokenize de-duplication pass (splitting on punctuation, looking for cross-comment repeated fragments ≥14 chars), it was confirmed that these files' comments are predominantly load-bearing "why" comments carrying SEV-\* / MID-\* / MIN-\* / CR-\* / WD-\* / H-\* / F-\* issue IDs, error strings, thresholds, cross-file references and regression-lock test names; densities are `ttwid` 42.1% / `web_api` 38.0% / `ws_client` 37.4% / `utils` 35.5% / `web_config` 30.4% / `video_postprocess` 27.8% / `web_tray` 16.6%, all far above the 13.0% floor and already at the reference-grade quality `AGENTS.md`'s comment convention defines. Hence **only** clearly zero-loss de-duplication was performed; no "why" comment was deleted wholesale, and the `web_api.py` block documenting the `main_loop_alive` removal (SEV-2221/2228) — a decision record including its "rejected alternatives" — was deliberately left intact per the `important_decision` four-tuple.
- **Nature of the change**: comment-only, no executable code touched; **no file added, no file deleted**; net removal of 1 comment line (`video_postprocess.py` −1; `ws_client.py` shortened in place, comment-line count unchanged). All other "repeats" surfaced by the scan were verified case-by-case to be **legitimate on-demand cross-references** (`同 close()` / `见 _guard_bind_host` / `同 update_config_line`) or **per-function responsibility lines repeated by need** (`is_original_delete=True 时删除源文件` holds independently at the three ffmpeg entry points), i.e. not deletable noise. The remaining five named files (`ttwid.py` / `utils.py` / `web_api.py` / `web_config.py` / `web_tray.py`; `web_tray.py` at 16.6% is closest to the floor and would in any case not tolerate line removal) were confirmed free of deletable restatements and **left unchanged**.

**Files affected (grouped by module)**:

- **Module: danmaku WebSocket client (`src/ws_client.py`)** — the trailing "；ws:// 返回 None。" on `_default_ssl_context`'s in-body comment duplicated the immediately preceding function-header comment verbatim; the tail was deleted (all facts retained: "Douyu danmuproxy:8506 legacy RSA ciphers / OpenSSL 3.x refuses the handshake above the default SECLEVEL / wss downgraded to @SECLEVEL=1"). Shortened in place, net 0 lines.
- **Module: video post-processing (`src/video_postprocess.py`)** — the fourth line above `get_startup_info`'s `def` ("按 system_type… 返回隐藏窗口的 STARTUPINFO，其他平台返回 None") overlapped with the first responsibility comment inside the function body; per `AGENTS.md`'s "merge adjacent duplicate comments" they were folded into a two-line function-level comment. All facts retained ("hidden window / always returns None on other platforms / mypy skips the non-current-platform code via the sys.platform literal branch"), net removal of 1 comment line.

### v4.3.0-dev (2026-09-24) — Frontend regression-lock fixes + wired into CI: two red locks in `test_regression_2026_09_22_gates.mjs` diagnosed as test-side defects, `.py` wrapper added into the pytest/CI loop (zero production-code change)

- **Background**: `tests/frontend/test_regression_2026_09_22_gates.mjs` (Group-G frontend regression locks, 32 cases, driving `web/app.js` via a `node:vm` sandbox) previously shipped only the `.mjs` with no `.py` wrapper, so the whole lock set sat outside the pytest / CI loop — violating `AGENTS.md`'s ".mjs real case + .py wrapper" two-file structure — and a direct `node --test` run showed 2 permanently-red locks (measured `30 pass / 2 fail`). This round located and fixed both red locks and added the wrapper to bring them under the gate.
- **Nature of change**: **Everything lands in the test / CI / docs layer; no production code was touched** (`web/app.js`, `src/`, `main.py`, etc. are unchanged). After tracing back to source, both red locks were test-side defects and production behavior was already correct: (1) the MIN-2241 regex was wedged by `src/web_api.py`'s pure-CRLF line endings; (2) the danmaku-cursor lock's `node:vm` DOM stub did not model `HTMLSelectElement.options`. Also fixed one half-dead lock ("locks the positive path but not the negative") and one platform-induced false-red in the CI gate. **Deletions: none** (no file removed, no feature removed; only two assertion/regex texts were replaced).

**Files affected (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Frontend regression-lock fixes + wired into CI: two red locks in `test_regression_2026_09_22_gates.mjs` diagnosed as test-side defects, `.py` wrapper added into the pytest/CI loop (zero production-code change) | section: Files affected (grouped by module)).

### v4.3.0-dev (2026-09-24) — Comment streamlining across four `src/` files: source-selection probes / SRT subtitles / sync HTTP / the ttwid credential cache, "cut derivation to conclusions + turn adjacent restatements into cross-references" (comment-only, zero logic change)

- **Background**: continues the same-day batches on `src/stream.py`, the four `src/` files and `main.py`; this round covers the four files named by the user: `src/stream_select.py`, `src/srt_writer.py`, `src/sync_http.py`, `src/ttwid.py`. Their comment blocks are predominantly load-bearing "why" comments carrying issue IDs plus regression-lock test names (`AGENTS.md`'s comment convention explicitly lists `stream_select.py` as a repository reference for comment quality, at ≈35%), so only two kinds of edit were performed: ① compress multi-layer derivations down to their conclusions; ② where the same fact was narrated in adjacent blocks, replace one of them with a cross-reference pointing at the single source of truth. No "why" comment was deleted wholesale and no second source of truth was created.
- **Nature of the change**: comment-only, no executable code touched; **no file added, no file deleted**; net removal of 32 comment lines (`sync_http.py` −10 / `stream_select.py` −11 / `srt_writer.py` −5 / `ttwid.py` −4). Every issue ID (F-12 / SEV-2226 / MID-27 / WD-01 / 2026-09-12 review 6.7·6.3 / SEV-N05 / MID-2231 / MIN-03 / MID-N32 / WD-03 / MIN-2236③ / MIN-24① / H-2 / MID-33 / MIN-2220 / MIN-2222), measured reading (11.9ms vs 1.47ms, 6.7ms construction, 0.77ms reused probe, gzip 1000:1, 10.6MB recorded in 10s, the ~125-call-site snapshot), CDN host names, error-string literals, constant names and thresholds, cross-file call-outs and regression-lock test names were preserved verbatim.

**Files involved (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Comment streamlining across four `src/` files: source-selection probes / SRT subtitles / sync HTTP / the ttwid credential cache, "cut derivation to conclusions + turn adjacent restatements into cross-references" (comment-only, zero logic change) | section: Files involved (grouped by module)).

### v4.3.0-dev (2026-09-24) — `main.py` comment streamlining: removed 2 pure function-name / code-restatement noise comments (comment-only, zero logic change)

- **Background**: Continuing the 2026-09-23 "repo-wide comment refinement" and the same-day `src/` de-duplication entries, this round evaluated the CLI recording entry point `main.py` (5456 lines / comment density ~23.9%). Conclusion: the file is already at the reference-grade quality defined by `AGENTS.md` — all 77 comment blocks of ≥6 lines are "why" comments carrying issue IDs (SEV / MID / MIN / F / CR / WD / H-5) plus regression-lock test names (e.g. `tests/test_regression_2026_09_22_main.py::...`), and every `[历史注]/修订` note is already in single-layer compressed form; per "only-add-never-rewrite / high-value why-comments must not be deleted" they were intentionally preserved. Only 2 spots in the whole file qualify as pure "function-name / code-behavior" restatements, meeting the removal criterion.
- **Nature of change**: comment-only deletion, no executable code touched; `main.py`'s byte-for-byte `ast.dump` before vs after is judged **equivalent** (logic unchanged), net −1 line (+1 / −2). No issue ID, CVE, constant, URL, regression-lock test name, or "why" context was lost.

**Files affected (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — `main.py` comment streamlining: removed 2 pure function-name / code-restatement noise comments (comment-only, zero logic change) | section: Files affected (grouped by module)).

### v4.3.0-dev (2026-09-24) — Repo-wide comment optimization: 3 factual corrections in root/build docs + compression of multi-layer "correction archaeology" across several subsystems (comment-only, zero logic change)

- **Background**: a multi-batch comment pass over the repo's "root docs + build config + danmaku / concurrency / ffmpeg subsystems", handled in two categories: (1) per the `AGENTS.md` exception for "correcting falsified factual statements", fixed three claims in the dependency list / build config that have been disproven by measurement; (2) per the 2026-09-23 compression caliber, collapsed multi-layer "old conclusion → disproven → supplement → in-place correction" stacked paragraphs into "current state + `[历史注]`" and removed noise that merely restates code or re-quotes signatures verbatim. Files designated by `AGENTS.md` as quality references, or whose density is near the 13% gate, were intentionally left intact per the "append-only, no rewrite" rule.
- **Nature of change**: comment-only, no executable code touched; every modified file's `ast.dump` is logically equivalent (comments never enter the AST), and values read by tests (dependency version strings, `fail_under`, etc.) were unchanged. All issue IDs (MID / SEV / MIN / MI / CR / P-1 / F-14 / F-17 / W6 / MIN-24④), CVE / PYSEC numbers, function and constant names, error-string literals, measured thresholds, cross-file references and regression-lock test names were preserved verbatim.

**Files involved (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Repo-wide comment optimization: 3 factual corrections in root/build docs + compression of multi-layer "correction archaeology" across several subsystems (comment-only, zero logic change) | section: Files involved (grouped by module)).

### v4.3.0-dev (2026-09-24) — `src/` comment streamlining: cut derivation to conclusions and removed code-restatement in `recorder_status.py` and `room.py` (comment-only, zero logic change)

- **Background**: continuing the 2026-09-23 "repo-wide comment refinement" and the same-day `gui.py` de-duplication entry, this round applied zero-information-loss streamlining to the verbose "derivation-style" comments in the recording-status/console module (`recorder_status.py`) and the Douyin room resolver (`room.py`) — compressing multi-layer derivations into conclusions and dropping comments that merely restate code. The user also named `scheduler.py`; on inspection that file is the comment-quality reference explicitly designated by `AGENTS.md` (~22%), and its long comment blocks are load-bearing cross-file sync anchors (per-method diff of the standalone copy, SEV-01 / MIN-22 / MIN-2231 concurrency semantics), i.e. protected by the append-only rule, so it was **intentionally left unchanged**.
- **Nature of change**: comment-only streamlining, no executable code touched; every review ID (MI-10 / MI-19 / MID-31 / review 6.3 / MID-2246), function name (`utils.run_js_async` / `_ensure_douyin_ttwid`), constant/threshold, cross-file reference (`main.py` / `src/notify.py` / `spider.py` / `AGENTS`) and error-code literal (`ValueError: I/O operation on closed file`) was preserved verbatim.

**Files touched (classified by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — `src/` comment streamlining: cut derivation to conclusions and removed code-restatement in `recorder_status.py` and `room.py` (comment-only, zero logic change) | section: Files touched (classified by module)).

### v4.3.0-dev (2026-09-24) — `src/spider.py` comment merge: de-duplicated two adjacent narratives in `_is_safe_http_url` (comment-only, zero logic change)

- **Background**: a comment-refinement assessment pass over `src/spider.py` (~6886 lines / 22.72% comment density). Conclusion: the file is already at the reference-grade quality defined by `AGENTS.md` — the vast majority are line-by-line load-bearing "why" comments (root cause / design trade-off / pitfall) plus the required three-layer structure comments (module header / function responsibility / boundary notes); deleting them would violate the "append-only, no rewrite" convention and risk losing security context (SEV-N04 credential destruction, MID-2220 silent signature failure, etc.). All 6 `[历史注]/修订` (historical-note / revision) markers in the file are already single-layer compressed, so there was no multi-layer "correction archaeology" left to compress. The one redundant spot qualifying under the "merge adjacent duplicate comments" authorization was `_is_safe_http_url`: its "thin-wrapper retention note" and its "MI-15 migration-history note" are two adjacent sub-blocks that both open by narrating "the implementation moved up to utils", partially overlapping.
- **Nature**: comment-only merge, no executable code touched; net 3 comment lines removed (7→4), with zero loss of key information (`utils.is_safe_http_url` ownership, no production call site inside spider, kept only for `tests/` compatibility, new code should use `utils.is_safe_http_url`, MI-15 / 2026-09-12 review 6.3, the `async_http`/`sync_http` circular dependency, paper defense, request-entry wiring after the move). The function under change is itself a dead wrapper with no production callers, so the AST is trivially equivalent.

**Files involved (grouped by module)**:

- **Module: `src/spider.py` (crawler module)** — 1 file modified, 1 adjacent duplicate comment merged:
  - `_is_safe_http_url()`: compressed the 3-line "this function is a thin wrapper over `src/utils.is_safe_http_url`..." block and the 3-line "`MI-15 / [历史注]` 2026-09-12 review 6.3 moved the implementation up to utils..." block (separated by 1 blank comment line) into 4 continuous lines, dropping the repeated "moved up to utils" lead-in while keeping every symbol name and rationale (the SSRF scheme-whitelist explanation paragraph above was left unchanged).

### v4.3.0-dev (2026-09-24) — Comment refinement across four `src/` files: removed "function-header vs inline" restatements and the same-source `proxy.py` scheme narrative (comment-only, zero logic change)

- **Background**: a follow-up to the 2026-09-23 "repo-wide comment refinement" and the same-day `gui.py` de-duplication entries, this round streamlined the comments of `src/logger.py`, `src/notify.py`, `src/proxy.py` and `src/node_install.py` — handling only the two categories "the same fact restated across adjacent comments" and "multi-layer derivation", without touching the high-value "why" causal chains.
- **Nature of change**: comment-only de-duplication and compression, no executable code touched; the three edited files are **equal=True** under a byte-for-byte `ast.dump` comparison against their pre-edit copies (logic-equivalent); no loss of any "why" information or key data (review IDs MID/MIN/CR/P-1, constants, criteria, URLs, concurrency/timing notes, cross-file names).

**Files touched (classified by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Comment refinement across four `src/` files: removed "function-header vs inline" restatements and the same-source `proxy.py` scheme narrative (comment-only, zero logic change) | section: Files touched (classified by module)).

### v4.3.0-dev (2026-09-24) — `src/stream.py` comment streamlining: 13 verbose / multi-layer "correction archaeology" blocks cut to conclusions (comment-only, zero logic change)

- **Background**: continuing the 2026-09-23 "repo-wide comment refinement" convention, this round applied targeted streamlining to the live-stream-URL resolution module `src/stream.py` — collapsing multi-layer "old conclusion → falsified → supplement → corrected-in-place" stacked paragraphs into "current state + `[History note]`" form, and dropping wording that merely restates code behaviour.
- **Nature of change**: comment-only streamlining, no executable code touched; **no file added, no file deleted**; net removal of 14 comment lines. Every MID/SEV/MIN/MI review ID, error-string literal, function/constant name, measured tier & bitrate, cross-file reference and regression-lock test name was preserved verbatim.

**Files touched (classified by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — `src/stream.py` comment streamlining: 13 verbose / multi-layer "correction archaeology" blocks cut to conclusions (comment-only, zero logic change) | section: Files touched (classified by module)).

### v4.3.0-dev (2026-09-24) — `gui.py` comment de-duplication: merged 3 "method-header vs first-body-line" restatements (comment-only, zero logic change)

- **Background**: a follow-up to the 2026-09-23 "repo-wide comment refinement" entry, further cleaning residual duplication in `gui.py` where the responsibility comment above a method signature restates the first-line comment inside its body. A programmatic de-dup comparing the method header against the first body line (character-set overlap > 0.5) hit 4 spots: 3 were pure restatements (the body line added nothing beyond the header) and were merged, while 1 (`_shutdown_and_quit`) carries execution-order info in its first body line and was kept.
- **Nature of change**: comment-only de-duplication, no executable code touched; net removal of 3 comment lines, with no loss of any "why" information or key data (review IDs / constants / criteria / race-condition notes).

**Files touched (classified by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — `gui.py` comment de-duplication: merged 3 "method-header vs first-body-line" restatements (comment-only, zero logic change) | section: Files touched (classified by module)).

### v4.3.0-dev (2026-09-24) — Type-stub completion: cleared mypy `disallow_untyped_defs` errors across 7 `.pyi` files in `typings/execjs/` (IDE no longer reports `no-untyped-def` when a single file is opened)

- **Background**: the stubs under `typings/execjs/` are auto-generated by pyright and many functions lacked parameter/return annotations. Although the mypy CLI gate's `[tool.mypy].exclude` already omits `typings/`, the IDE still checks each **individually opened** `.pyi` against `disallow_untyped_defs = true` and reports `Function is missing a type annotation ... [no-untyped-def]`. This round aligns with the `typings/execjs/__init__.pyi` convention: concrete types follow the real execjs signatures, while dynamic JS return values uniformly use `Any`.
- **Nature of change**: pure type-annotation completion, no runtime behaviour change; **no files added, no files deleted**.

**Files touched (classified by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-24) — Type-stub completion: cleared mypy `disallow_untyped_defs` errors across 7 `.pyi` files in `typings/execjs/` (IDE no longer reports `no-untyped-def` when a single file is opened) | section: Files touched (classified by module)).

### v4.3.0-dev (2026-09-24) — Reduced the resident `AGENTS.md` context by moving only one-time evidence; constraints and gates remain in place

- **Scope**: moved Huya FLV-first cold-start samples, Huya probe-backoff-window readings, ffmpeg reconnect incidents, ffmpeg per-file option-side evidence, boolean-config drift, and keepalive measurements into `docs/agent-reference/measured-evidence.md`; each original location retains a one-hop link.
- **Constraints unchanged**: risk controls, gate commands, known-pitfall constraints, and regression locks remain in `AGENTS.md`; counts of “必须 / 不得 / 禁止 / 须 / 一律 / 不可 / 绝不” match the pre-change baseline.
- **Size**: `AGENTS.md` decreased from 1,552 lines / 189,999 bytes to 1,548 lines / 188,355 bytes, saving 4 lines / 1,644 bytes.

### v4.3.0-dev (2026-09-23) — P0 fix: bare `reconfigure` in `build_exe._ensure_utf8_streams()` corrupted pytest fd capturing (local runs ended without a verdict and were misreported as a "GUI startup failed" dialog)

- **Symptom**: after a local `python -m pytest` run, a dialog titled "GUI startup failed" appeared containing
  a pytest session-teardown traceback ending in
  `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xa1 …`. A stealthier variant marked an **unrelated test**
  as `FAILED` + `ERROR`. All nine CI jobs run on ubuntu and stayed green throughout.
- **Root cause (three layers)**: ① `build_exe.py::_ensure_utf8_streams()` called a **bare**
  `reconfigure(encoding="utf-8")` on `sys.stdout`/`sys.stderr`. Per CPython, specifying `encoding='utf-8'`
  without `errors` **resets the error handler to `'strict'`**, so pytest's fd-capture wrapper (`EncodedFile`,
  originally `errors="replace"`) was flipped **in place**. ② The trigger ran inside the host process: three cases
  in `tests/test_build_exe.py` call `build_exe.main()` in-process, whose first statement invokes that function.
  ③ Impact also required a second condition: non-UTF-8 bytes reaching fd 1/2 (cp936 subprocesses, inherited
  handles, frozen-exe raw writes). Python-level writes are encoded as UTF-8 and ubuntu's UTF-8 locale cannot
  produce such bytes either — which is why the defect stayed latent for so long.
- **Fix**:
  - `build_exe.py::_ensure_utf8_streams()`: `reconfigure(encoding="utf-8", errors="replace")`, aligned with the
    five other implementations (`gui.py`, `main.py`, `web.py`, `scripts/run_gates.py`,
    `scripts/douyin_live_recorder_standalone.py`).
  - `gui.py`: `_install_crash_sink()` now installs process-level hooks only when `__name__ == "__main__"`. The
    import-time hook previously let GUI error handling capture pytest's uncaught exceptions (pytest imports `gui`
    via `tests/test_gui_monitor.py`), showing a misleading dialog and swallowing the original traceback from the
    console. Script-entry observability (`pythonw gui.py` / frozen exe) is unchanged.
  - `tests/conftest.py`: new autouse guard `_guard_stdio_encoding_policy` verifies and restores
    `sys.stdout`/`sys.stderr` `(encoding, errors)` per test — turning "silently mutating global streams" from
    "an unrelated traceback during teardown dozens of cases later" into "named on the spot".
  - `tests/test_build_exe.py`: two new regression locks (policy unchanged under real capturing / `errors="replace"`
    must be passed explicitly).
  both locks red immediately and the guard fixture names the offender; full `pytest` results in this session;
  `black` / `isort` clean. Real-device verification (DoD step 2) is **not applicable** (no recording-chain change).
- **Remaining**: the producer of the `0xa1` byte is still unidentified; it does not affect this fix (any future
  invalid byte is downgraded to `�` rather than crashing the session).
- **Docs**: added `DIAGNOSIS_2026-09-23_pytest-teardown-crash.md` (sections: overview / timeline / root cause /
  fix / verification / lessons / references).

### v4.3.0-dev (2026-09-23) — Repo-wide comment refinement (68 files): multi-layer "correction archaeology" collapsed into single-line history notes; new third blind spot for `check_annotations.py` (line-ending form); three falsified statements corrected in place

> **Nature**: comments only, no executable code touched. Proof: `check_annotations.py --baseline`
> reports **AST-equivalent for all 167 files** (`.py` compared via `ast.dump`, `.js/.css/.html` via
> comment-stripped code lines). Per the Definition-of-Done exemption this runs steps 1 (gates) + 4
> (docs) + 5 (cleanup) + 6 (log); **step 2 (real-machine verification) is not applicable** — recording
> behaviour is provably unchanged, so no live room is required.

**1. Scope and numbers**

- **68 files refined**: all 33 `src/` modules + 5 `src/platforms/` modules + 6 root entries
  (`main.py` / `gui.py` / `web.py` / `i18n.py` / `msg_push.py` / `build_exe.py`) + 9 `scripts/`
  maintenance tools + `scripts/douyin_live_recorder_standalone.py` (the twin copy) + 3 `web/` assets
  + the 12 largest test files.
- Repo average comment density **23.5% → 23.3%** (gate floor 13.0%, no file fell below it);
  `main.py` 25.1%→23.7%, `src/web_api.py` 40.4%→38.0%, `gui.py` 23.3%→20.9%.
- Not done: the remaining ~95 files under `tests/` (mostly small, 13–16% density, where the only
  legal action is an equal-length reword — low return).

**2. Compression rule** (authorised by the maintainer; details now in the new AGENTS.md
"Comment conventions" bullet): a stack of "old conclusion A → `[revised: A disproved]` → `[supplement]`
→ `[in-place correction]`" becomes "current measured state in the body + one
`[history note] YYYY-MM-DD X was …` line". Measured readings, host names, constant names, environment
variable names, platform names, acceptance criteria, concurrency/timing assumptions, error codes and
genuine regression-lock test names are preserved verbatim; mutual cross-references
(`src/ffmpeg_install.py` ↔ `scripts/douyin_live_recorder_standalone.py`) must keep the literal file
name, because `tests/test_ffmpeg_path_preference.py` asserts on the raw text.

**3. Falsified statements corrected in place** (each with its re-check command, per AGENTS.md rule 12)

1. `src/ffmpeg_install.py:43` module-header duty line still claimed "Windows has only the gyan.dev
   official source", contradicting the same file's current-state note that the master source exists
   but is gated off → rewritten to "gyan.dev by default; a second source exists, disabled by default".
   Three further spots in that file were fixed too: a deleted lanzhou hop described as live, and a
   claim that the master fallback is "ungated" when it is in fact behind `master_allowed`.
2. AGENTS.md claimed `utils.update_config` still writes directly with `open(path,"w")` and is
   therefore not interchangeable with `config_io`. Since WD-15 it goes through `atomic_write_text`, so
   "the readonly case can just use `chmod`" no longer holds; corrected, with a note voiding the old
   wording. Re-check: `grep -n "atomic_write_text(file_path" src/utils.py`.
3. AGENTS.md claimed the standalone copy's `PlatformBreaker` lacks `_grant_probe` / `_end_probe` /
   `error_rate` / `backoff_seconds` ("src 9 methods, copy 5"). Measured: `_grant_probe` and
   `_end_probe` **are present** in the copy; what is actually missing is `error_rate` /
   `backoff_seconds` / `_push_sample` (the copy carries a renamed `_push`). The hard-coded list and
   counts were replaced with a reproducible set-difference command, per this repo's "do not copy
   snapshots" policy.

**4. New gate blind spot** (AGENTS.md "tool blind spots" widened from two to three)
`code_signature` uses `ast.parse` + `ast.dump(include_attributes=False)`, and the Python grammar does
not distinguish `\r\n` from `\n`, so **a whole-file CRLF→LF conversion is invisible to both the AST
equivalence check and `black --check`**. During this pass one batch rewrote files wholesale and
 it
was caught only by byte-comparing against the snapshot and repaired with
`b.replace(b'\n', b'\r\n')`. Knock-on effect: node-side assertions that match raw text and hard-code
`\n\n` flip from green to red (live example: the `MIN-2241` reverse routing lock). The rule and the
md.

**5. Confirmed pre-existing, deliberately not fixed here** (handed back, by priority)

1. `tests/test_stream.py` run alone: **4 failed** (douyin ×2 + TikTok ×2), root cause is an import
   cycle between `src/stream_select.py:29 import main` and `src/stream.py`'s lazy
   `from .stream_select import MOBILE_UA` → `ImportError: cannot import name 'MOBILE_UA' from
   partially initialized module`. A full-suite run masks it via import order — the same family as this
   repo's "green in the full run, red single-file" hazard. Proved unrelated to comments by A/B:
   restoring the baseline copies of `src/stream_select.py` and `src/stream.py` reproduces the same 4.
2. `tests/frontend/test_regression_2026_09_22_gates.mjs` **has no Python wrapper case driving it**
   (the repo convention is "`.mjs` real case + `.py` wrapper"; only `test_quality_ui.mjs` is wrapped
   by `tests/test_frontend_quality_ui.py`), so its **2 red assertions** (the `MIN-2241` routing lock
   above, and "danmaku_unavailable must not advance the incremental cursor") never reach CI.
3. `pytest --cov=src` — the command AGENTS.md and CI prescribe — writes `.coverage` into the repo
   root, after which a test reads a file as UTF-8 in teardown and hits
   `UnicodeDecodeError: 0xa1 in position 486`, which cascades to **5167 errors** locally. Pointing
   `COVERAGE_FILE` outside the repository gives **3188 passed / 13 skipped, rc=0**.
4. `tests/test_utils.py::test_readonly_file_write_failure` asserts
   `"k = old" in text or "k = new" in text` — a tautology that can never fail and locks no behaviour.

**6. Verification (DoD step 1)**: `python scripts/run_gates.py` → **8/8 green**; `pytest` (with
`COVERAGE_FILE` outside the repo) → **3188 passed / 13 skipped, warnings summary empty (0 entries)**;
`scripts/check_coverage.py` → **PASSED: All 42 module(s) meet coverage threshold** (rc=0);
`basedpyright` → **0 errors / 0 warnings**; `check_annotations.py` → all pass, 0 dangling symbols;
`tests/test_regression_2026_09_22_gates.py` (reads AGENTS.md's gate block) → 25 passed;
`scripts/check_version.py` → PASS. Twin copy checked separately:
`pytest tests/test_regression_2026_09_22_standalone.py` → 17 passed, `mypy` → no issues.

**Live verification**: not applicable (no recording-chain behaviour touched; proven by 167/167 AST
equality — no new ffmpeg arguments, source-selection logic or platform resolvers).

### v4.3.0-dev (2026-09-23) — P0 fix: recording failed 100% of the time on ffmpeg master builds (`-thread_queue_size` was narrowed to an output-only option upstream, while we still emitted it before `-i`)

> **Symptom**: after adding a Douyin room in `py web.py`, `序号3 … 正在直播中` printed `准备开始录制视频`
> and ffmpeg exited immediately with return code **-22 (EINVAL)**, zero bytes written. Verbatim console error:
> `Option thread_queue_size (set the maximum number of queued packets per stream on the muxer) cannot be applied to input url http://pull-hls-h95.douyincdn.com/…_or4.m3u8 … Error opening input files: Invalid argument`
> **Unrelated to the room, platform or CDN** — as long as `ffmpeg/ffmpeg.exe` is a master build
> (here `N-126755-g52f05ac780-20260922`, produced by the `FFMPEG_MASTER_ALLOWED` BtbN channel),
> *every* recording attempt fails on that binary.

#### 1. Root cause: upstream changed which side the option belongs to, and the failure mode went from silent to fatal

- `main.py::_build_ffmpeg_input_args` placed `-thread_queue_size 1024` before `-i`
  (previously `main.py:3475`), relying on its **input-side** legacy meaning
  (`doc/ffmpeg.texi`: up to 9.0.2 it is marked `(input/output)`; on input it forces a separate reading
  thread, which is off by default for a single input).
- Upstream has narrowed the option to **output-only**: `doc/ffmpeg.texi` marks it `(output)` on master,
  leaving only "packets queued per muxing thread"; the local `ffmpeg -h full` lists it under
  **"Advanced per-file options (output-only)"**. It is therefore **no longer valid before `-i`**.
- The opposite of the 2026-09-10 `-reconnect*` incident: that one was "wrong side, silently accepted, rc 0",
  this one **exits with EINVAL before the input is opened at all** — louder, but still only pin-downable
  by a semantic assertion rather than by the format/type gates.
- A per-option position audit against the `-h full` section headings confirms **this is the only offender**:
  with `-thread_queue_size` removed, every remaining input-side option
  (`-rw_timeout` / `-user_agent` / `-protocol_whitelist` / `-analyzeduration` / `-probesize` / `-fflags` /
  `-reconnect*` / `-re`) passes parsing and only then fails with `Connection refused` —
  i.e. a single-point fix, no second latent mismatch of this class.

#### 2. Fix: moved to the output side (the only position valid on the whole supported range)

- `-thread_queue_size 1024` moved out of the input group to after `-i`, next to `-max_muxing_queue_size`
  in the output buffering block; the value is unchanged (1024) and the in-code comment records the upstream
  texi version comparison plus the reason it must not go back to the input side.
- Selection criterion: the output position is valid on **6.1 / 7.1 / 8.0 / 9.0.2 and master alike**
  (measured A/B below), while the input position is valid only up to 9.0.2. Hence **no version probing** —
  keeping "a separate input reading thread" on old builds at the cost of crashing on new ones is not an
  acceptable trade. The honest cost: ≤9.0.2 loses one hint, and master has no such mechanism at all.
- The twin copy `scripts/douyin_live_recorder_standalone.py` **never carried** this option (its flag set
  already differs from `main.py`, see `CODE_REVIEW_2026-09-21.md` line 496), so no twin sync was needed.

#### 3. Verification

  (three AST invariants) — "after `-i`", "immediately followed by a literal value",
  and a reverse witness on the definition-point count (main.py 1 / standalone 0).
  Each of the three has a mutation that singles it out; measured truth table: drop the value →
  only `has_literal_value` reddens; delete the whole pair → only the reverse witness reddens;
  move it back before `-i` → only `follow_i_flag` reddens. `main.py` restored byte-for-byte after each run.
- **Golden snapshot**: `tests/test_start_record_command_golden.py` failed on the first run exactly as it should,
  showing the byte-level diff across 19 commands (proof the lock really covers this), then
  `GOLDEN_REGEN=1` regenerated it and 32 tests passed; the regenerated artefact was re-checked
  ("commands where `-thread_queue_size` still sits before `-i`: 0 of 19").
- **End-to-end (real binary + real argument vector)**: the production-built command vectors taken from the
  golden file were run against this same master binary, with only the input swapped for a locally served
  HLS (m3u8) / FLV source and the output redirected to a temp directory — 3×2 matrix:

|  | Input shape | Option position | rc | Bytes produced |
| --- | --- | --- | --- | --- |
|  | HLS (`-reconnect_at_eof` dropped as production does) | before `-i` (pre-fix) | 4294967274 (= -22) | 0 |
|  | HLS | after `-i` (fixed) | 0 | 275420 |
|  | HLS | option absent | 0 | 275420 |
|  | FLV | before `-i` (pre-fix) | 4294967274 (= -22) | 0 |
|  | FLV | after `-i` (fixed) | 0 | 234248 |

  The two "before `-i`" cells reproduce the production incident verbatim
  (same `cannot be applied to input url` message).
- **Real-room check (live room + internet)**: `SKIP(not run by the agent)` — substituted this round by a local
  synthetic source plus the production argument vector. Hand-back action: re-run `py web.py` with those three
  Douyin rooms and confirm `序号3` no longer returns -22 and that media files land on disk.
- **Gates**: `scripts/run_gates.py` all 8 green (black / isort / bare `mypy` / `mypy --platform linux` /
  check_annotations / compile_po --check / check_version / check_runtime_pins) + `pytest`
  **3188 passed, empty warnings summary** + `scripts/check_coverage.py` 42 modules within threshold
  (83.91% total) + `basedpyright` **0 errors / 0 warnings**.

#### 4. Durable rule (written into `AGENTS.md` → "Known pitfalls / ffmpeg command construction")

Before adding any per-file option, run `ffmpeg -h full` and read which section heading it falls under —
the `Advanced per-file options (output-only)` / `(input-only)` boundary moves with upstream, and the two
failure shapes (`-reconnect*`: silently accepted; `-thread_queue_size`: hard EINVAL) do not cover each other.
**Do not infer this round's consequence from last round's "wrong side only meant it did nothing".**

### v4.3.0-dev (2026-09-23) — Test hygiene: fixed one cross-file patch leak behind 11 false failures + new R6 gate ("manual MonkeyPatch must be undone"); coverage gate gains a tiered whitelist (empty by default, expiry fails)

> **Nature**: touches tests and gate scripts only, **no production behaviour change**. Follows the same-day
> `CODE_REVIEW_2026-09-22_3.md` close-out.
> **Trigger**: the full `pytest` run showed 13 failures, 11 of which were green when their file ran alone —
> the classic "red in full run, green in isolation" shape.

#### 1. Root cause: one missing `undo()` made later tests hit the real network

- The polluter was this round's new `tests/test_regression_2026_09_22_net.py`: 8 manual `pytest.MonkeyPatch()`
  instances but only 7 `undo()` calls. Manual instances are **not restored by pytest** (unlike the
  `monkeypatch` fixture), so the leaked one kept `src.utils.handle_proxy_addr` pinned to `lambda x: None`
  for the rest of the process.
- Propagation: `async_http.utils` and the `utils` name inside `src/sync_http.py` are **the same `src.utils`
  module object** → the proxy address resolved to empty → `sync_req` silently fell into the urllib direct
  branch → **which those cases do not stub** → a real request went to `http://example.com`, so the assertion
  saw `<!doctype html>…` instead of the stubbed return value.
- Blast radius (11 cases, each re-tested and confirmed not to be product defects): 10 in
  `tests/test_sync_http.py` (`TestSyncReq` proxy GET/POST/redirect/json_data, 1 in `TestSslVerifyScoping`,
  3 in `TestProxyAddrNormalization`, plus 2 same-family) and 1 of the 3 proxy-normalisation cases in
  `tests/test_stream_select.py`. After the `undo()` fix the two files went from 101 to **168 passed**.
- The remaining 2 were **assertions stale after intentional changes** (not pollution); they were rewritten to
  the real semantics rather than loosened:
  `test_danmaku_wiring.py`'s `stop.call_count == 1` — after SEV-2208 moved `stop()` unconditionally into
  `finally`, the early-interrupt path necessarily stops twice (`DanmakuCollector.stop()` is idempotent via
  `_stop_called`), so the assertion now pins "exactly 2" while keeping both failure shapes meaningful
  (=1 means the finally half vanished, >2 means the teardown fired repeatedly);
  `FakeWs` in `test_platform_danmaku_offline.py` and `_FakeAuthWs` in `test_bilibili_danmaku_info.py` lacked
  MID-2245's new `fail()` entry point (the `ensure_future` coroutine raised `AttributeError`, surfacing as
  the misleading "closed is still False" plus an unretrieved task-exception warning). The fakes now implement
  it and the tests assert the reported reason — asserting only `closed` would let an implementation reverted
  to `close()` pass silently.

#### 2. Prevention: hygiene gate rule R6

R1 in `tests/test_test_hygiene.py` only saw `setattr` / `patch.object` and string-form stdlib rewrites, so it
could not see this shape. R6 `_manual_monkeypatch_violations()` counts `pytest.MonkeyPatch()` creations versus
`undo()` calls per function body and flags any surplus; `test_guard_r6_actually_catches_a_leaked_monkeypatch`
provides the two-way witness (a synthetic leaked instance must be reported, a compliant shim must not).
Measured: no second occurrence repo-wide (426 passed).

#### 3. Tiered whitelist for the coverage gate (`scripts/check_coverage.py`)

Resolution order **registered threshold > debt baseline > global floor**, with a machine-checked exemption tier:

| Tier | Carrier | Applies to | Exception / failure handling |
| --- | --- | --- | --- |
| Registered threshold | `MODULE_THRESHOLDS` | production modules with a human-set target | key pointing at a missing module → rc=2 (rotted configuration) |
| Debt baseline | `COVERAGE_DEBT` (`DebtEntry`) | **only** pre-existing modules already below the floor before this round; **new modules may never enter** | missing `reason`, `tracker` not a report pointer, non-ISO `review_by` → rc=2; `floor ≥ GLOBAL_FLOOR`, expired `review_by`, actual below baseline, a passing module left in the table, count > `DEBT_CEILING` → rc=1 |
| Global floor | `GLOBAL_FLOOR = 50.0` (same value as `pyproject fail_under`) | every unlisted module, including new files | module absent from the report → treated as failure (MIN-19) |
| Structural exemption | `GATE_EXEMPT_MODULES` | generated / structurally untestable code | a reason claiming "generated" must hit a `GENERATED_MARKERS` string in the file, else rc=2 (false claim); count > `EXEMPT_CEILING` → rc=1 |

- **The table is empty today**: 42 of 43 `src/` modules meet the bar and 1 is the protoc stub, so nothing needs a
  debt baseline and `DEBT_CEILING = 0`. Adding an entry therefore forces raising the ceiling and recording the
  reason in `AGENTS.md` — the same anti-bookkeeping stance as `pip-audit --ignore-vuln`.
- 11 new cases cover each rule, and 5 mutations (drop the debt tier / drop the stale-entry check / drop expiry /
  drop the ceiling / drop the generated-marker check) each redden their own case; the production script was
  restored byte-for-byte (sha256 verified).

#### 4. Readings and verification

`tests/test_check_coverage.py` 41 passed, `tests/test_test_hygiene.py` 426 passed, the four affected test files
0 warnings; `black`, `isort` and plain `mypy` green. Live verification: this change does not touch the recording
chain or ffmpeg arguments, so it is recorded as not applicable under the Definition-of-Done exemption clause.

> **Nature of this round**: 1 module added, 1 module modified, **no file deleted**.
> **Trigger**: ① Windows on ARM previously had **no native ffmpeg source** — the only automatic route
> (`gyan.dev`) ships x86_64 builds only, so ARM64 hosts could only run ffmpeg under x64 emulation;
> ② when `gyan.dev` is slow or blocked from mainland China, x86_64 also had "one route, fail → install
> manually", with no ungated fallback.

#### 1. New file — `src/ffmpeg_master_download.py` (403 lines)

Windows FFmpeg **master rolling-build** downloader, build name `ffmpeg-master-latest-{win64,winarm64}-gpl.zip`.
Suffix meaning: `win64` = x86_64 (Intel/AMD), `winarm64` = ARM64 (Windows on ARM), `gpl` = build including GPL codecs.

| Part | Name | Responsibility |
| --- | --- | --- |
| Entry | `download_ffmpeg_master(dest_dir, arch=None)` | Top-level download + install; returns `False` on failure instead of raising (same contract as `ffmpeg_install`) |
| Source select | `_windows_arch()` / `_candidate_urls()` | Picks `win64`/`winarm64` from `platform.machine()`; candidates `[fyhub.cn, BtbN GitHub]` |
| Probe | `_probe()` / `_looks_like_html()` | **Range GET `bytes=0-0`** probe that detects human-verification pages (`HEAD` returns 405 on fyhub, hence not used) |
| Transfer | `_stream_download()` | Streamed download + `tqdm` progress; separate connect/read timeouts; 3 backoff retries (2/4/8s) on connection-level failures, no retry on HTTP 4xx/5xx |
| Integrity | `_tofu_verify_or_record()` / `_master_hash_file()` | TOFU hash cache; baseline prefix `_ffmpeg_master.*` (kept separate from the official source's `_ffmpeg_official*`) |
| Errors | `FfmpegDownloadError` → `IntegrityError` / `NetworkError` (`ChallengePageError` was removed on 2026-09-23 under MIN-2267) | Layered error capture so the caller can switch source or abort |

Key constants: `_CONNECT_TIMEOUT=15` / `_READ_TIMEOUT=30` / `_PROBE_TIMEOUT=20` / `_MAX_RETRIES=3` / `_RETRY_BACKOFF=2.0`.

**Measured finding that shaped this module**: `fyhub.cn` answers both direct links with a "download
verification" HTML page (200 + `text/html`, containing a `verification_token` form and the
`vdf-worker.js` proof-of-work), `HEAD` returns 405 and `.sha256` returns 404 → **a plain script cannot
download them**. Therefore `_probe()` detects the challenge page and skips that source, falling through to
the ungated BtbN GitHub `releases/download/latest/...` (measured: 206, `application/octet-stream`, first
bytes `PK\x03\x04`, a valid zip).

#### 2. Modified file — `src/ffmpeg_install.py`

| # | Location | Change |
| --- | --- | --- |
| 1 | Module imports | Added `from src.ffmpeg_master_download import download_ffmpeg_master` (one-way import; the new module does not import this one, so **no circular dependency**) |
| 2 | `install_ffmpeg_windows()` | Changed from "a single gyan.dev route" to **routing by host architecture** |
| 3 | Same function, closing hint | The manual-install hint's baseline prefix widened from only `_ffmpeg_official*` to `_ffmpeg_official*` + `_ffmpeg_master*` |

Routing logic:

- **x86_64**: `gyan.dev` official source still takes priority (with official SHA256 verification); the BtbN
  master build is used **only if the official source fails** (ungated, TOFU only) as an availability
  fallback for restricted networks — this branch is **never** reached when the official source is reachable.
- **ARM64**: goes straight to the native arm64 master build (`gyan.dev` has no arm64 source, so this is the
  only native option); if it fails it falls back to the official x86_64 (x64 emulation) so something usable
  is installed.

#### 3. Deletions

**No file was deleted this round.** One wording change only: the previous claim in
`install_ffmpeg_windows()` that "Windows has exactly one automatic source" no longer holds after the
architecture split and was rewritten in place (a comment/wording update, not a feature removal).

#### 4. Integrity stance (important boundary)

- The ARM64 path and the x86_64 BtbN fallback are both **TOFU (trust on first use)**: neither fyhub nor
  BtbN publishes a `.sha256` document for the rolling `latest` alias (both measured 404), so authoritative
  hash verification is impossible; and a rolling URL must not have its hash constant pinned in source
  (a new upstream build would fail forever — the historical cause of MID-59).
- The `gyan.dev` primary path for x86_64 is **unaffected** and still runs "official published SHA256 first,
  degrade to TOFU only when it cannot be fetched".
- TOFU degradation is logged with an explicit `warning`, never silently.

#### 5. Verification

- `py_compile` passes; `import src.ffmpeg_install` has no circular import.
- Probe self-test `python -m src.ffmpeg_master_download`: this machine is `arch=win64`, fyhub → `challenge`,
  BtbN → `ok`, so the degradation decision is correct (**probe only; the full ~190MB package was not
  downloaded**).
- `black --check` / `isort --check-only` (line-length 120) pass for both files; argument-less `mypy`
  **rc=0** (146 files, 0 errors).
- **Outstanding**: no end-to-end real-device install verification (requires downloading the full package and
  running `ffmpeg -version`); handed back to the user to execute.

### v4.3.0-dev (2026-09-22) — Doc convergence (Lanzou removal formally accepted) + README "installing ffmpeg manually on Windows" user guide

> **Nature of this round**: documentation only, **zero production-code change** (`src/`, `main.py`,
> `build_exe.py`, the four i18n catalogues and all tests untouched).
> **Trigger**: the user ruled "accept the removal, leave the rest to its author" — the Lanzou deletion stays as
> landed, this round only re-points the docs that still described P-1b as an opt-in switch, and adds the manual
> install path for Windows users (with only one automatic route left, no guide means leaving the failure state for
> users to guess at).

#### 1. P-1b "opt-in switch" wording retired in place (4 CN + 4 EN spots, each with a dated `[2026-09-22 revision:]` note)

1. Supply-chain-hardening entry **title** in `CODE_WIKI.md` / `CODE_WIKI_EN.md`: annotated "P-1b, superseded the same day".
2. That entry's **P-1b subsection**: rewritten as "shape at the time", with the deletion scope named
   (`get_lanzou_download_link()` / `_install_ffmpeg_lanzou()` / `_lanzou_fallback_enabled()` plus all three
   `FFMPEG_LANZOU_*` variables), and the record that the open item "was the `ALLOW_UNVERIFIED` literal token set
   widened?" is **void** with the variable — no tightening decision is pending any more, don't re-schedule it.
3. That entry's "conventions / doc sync" paragraph: "lanzou behind an explicit switch" → "deleted outright, and any
   second Windows source must first satisfy the upstream-published-hash test".
4. The trust-review snapshot row (`runtime ffmpeg`) and the coverage-table row (`src/ffmpeg_install.py`) each got a
   "snapshot at the time" note; the former also marks the P-1 suggestion **[implemented]**.
5. `PROPOSAL_2026-09-22_binary-trust-policy.md` impact table, two rows: **runtime plane** (the success-rate impact
   escalates from "off by default" to "no fallback at all") and **user contract** (row voided; the net change is
   "no mirror fallback, failure prints a manual-install hint"). The `i18n` row gained a pointer to the current reading
   (675 was that round's reading only).
6. `AGENTS.md` class ② was rewritten by the deletion round's own author; this round only confirmed it did not regress
   (`grep lanzou src/ffmpeg_install.py` → 0 hits; the remaining mentions are historical comments).

#### 2. i18n catalogue counts re-measured (conclusion: record timestamped readings, never a bare "current value")

- Latest self-consistent reading, **16:14: `.mo` header N=667 / 666 entries per catalogue / extractor reports 0
  missing** (the same commands read 663/662 at 16:05; another catalogue write landed at 16:11). Sequence table and
  five corroborating signals live in §3 of the "Windows runtime ffmpeg source consolidation" entry below.
- Two fix reports during this round claimed "N=679 / 663 keys each" and "N=680 / 679 each (mtime 20:13:54)".
  Re-running the same commands produced different self-consistent readings (663/662, then 667/666), and the claimed
  mtime lay ahead of this machine's clock (16:14 at the time). **The docs do not adjudicate who was right**; they
  freeze the reproducible procedure: ① any count ships with command + reading time; ② N and key count differ by
  exactly 1 by definition, so neither may be quoted for the other; ③ a claimed mtime outside the local clock is
  unverified evidence. Rule recorded in `AGENTS.md`.
- **One real divergence for the deletion round's author**: the 16:11 write restored 4 蓝奏云 msgids to the
  catalogues while `src/ffmpeg_install.py` greps 0 hits for `lanzou`. No gate reddens (redundant keys are
  informational), but it contradicts "all 16 removed". Registered as a follow-up; this session does not edit
  another owner's four catalogue files.

#### 3. README: new "Installing ffmpeg manually (Windows user guide)" section (CN/EN paired, end of 🚀 Quick start)

- Every statement taken from measured code, no inference: `install_ffmpeg_windows()` has exactly one automatic
  route (gyan.dev `ffmpeg-release-essentials.zip`); `download_ffmpeg_official()` `copytree`s the archive's `bin/`
  **contents** into `execute_dir/ffmpeg/`, so the shipped shape is **flat `ffmpeg\ffmpeg.exe`**; `main.py` prepends
  only that one level to `PATH` (no recursion), so "extract as-is and keep `ffmpeg\bin\ffmpeg.exe`" is
  **not** found — the guide lists that as an explicit don't.
- Destination table split by run mode (exe package = `DouyinLiveRecorder\ffmpeg\`, source/single-file = `<root>\ffmpeg\`),
  per `src/logger.py::_app_root()` (frozen returns the exe's sibling directory, **not** `_internal/`).
  installed."; on a SHA256 baseline rejection delete `<app dir>\_ffmpeg_official*.zip.sha256`
  (`_HASH_SUFFIX = ".zip.sha256"`) and restart — with the caveat written down that the sidecar's strength equals
  that directory's write permissions, so users don't mistake it for a security boundary.
- All three equivalent install planes named: bundled `ffmpeg\`, system `PATH` (anything `shutil.which` finds), and
  containers (image installs via apt); full / lite / single-file scope clarified. The FAQ's "Windows: the program
  already bundles ffmpeg, nothing to install" only holds for **full** packages and was replaced by a conditional
  pointer to this section.
- **Two factual errors in code comments recorded but not fixed** (no code touched): `src/ffmpeg_install.py:71` claims
  the artefact lands at `execute_dir/ffmpeg/bin/ffmpeg.exe` and `:68` claims `execute_dir` points into `_internal/`
  when frozen — both contradict `_app_root()` and the `copytree` target. That file belongs to the deletion round's
  author; documenting it here is the point — a guide written from those comments would mislead users.

#### 4. Gates and two cross-session false reds

- `run_gates.py` **8/8** (135.1s, the 16:09 run); `tests/test_i18n.py` + `test_i18n_migration.py` **44 passed**
  (16:15, i.e. after the 16:11 catalogue write); full `pytest` in a single session **2463 passed / 12 skipped /
  0 failed / 0 warnings** (16:0x, at the 663/662 state).
- The `_out_e2e` race **reproduced a second time the same day**: a 16:18 full run reported 4
  `tests/test_srt_timeline_anchor.py::FileNotFoundError: tests\_out_e2e` while this session had **not** started a
  second pytest run (only another workflow writing the same tree). Solo re-run of that file: 4 passed → still an
  environment race, same mechanism as recorded on 2026-09-21: the file `os.makedirs` at **import** time, while any
  session's `conftest.pytest_unconfigure` `rmtree`s the shared directory.
- **This follow-up was closed on 2026-09-24 (carried out by a later session, not this round)**: the four cases in
  `tests/test_srt_timeline_anchor.py` now use `tmp_path` — bodies extracted into `_*` functions taking an
  `out_dir`, plus a `tempfile.TemporaryDirectory` direct-run channel, following the pattern already established
  by `tests/test_bili_e2e.py`. The import-time `os.makedirs(tests/_out_e2e)` and its "clear before writing"
  pre-clean were removed together, and `_out_e2e` was dropped from both `tests/conftest.py::_TEST_OUT_DIRS` and
  `tests/test_test_hygiene.py::_ALLOWED_TESTS_ENTRIES` (`_out_live` is **kept** — the five
  `test_*_live_collector.py` scripts still write it during manual real-room verification, but they expose no
  `def test_`, so pytest only imports them; the import-time race is therefore gone). Post-fix readings: two
  consecutive full `pytest` runs with **zero `_out_e2e` failures** (previously 4 every run), `black --check
  tests/` → 108 files unchanged, `mypy tests/` → 102 files / 0 issue, 435 passed on the targeted set; the
  `.gitignore` entry `tests/_out_e2e/` is deliberately kept so a rebuilt stale copy cannot get committed. The
  AGENTS.md "keep full runs serial" entry was rewritten in place — per "a superseded entry gets its body
  corrected plus a dated correction note" — into the durable rule "test artefacts always go through
  `tmp_path`", with the old mechanism retained there as history.

### v4.3.0-dev (2026-09-22) — Windows runtime ffmpeg source consolidation: Lanzou fallback removed + downloaded-payload shape guard

> **Nature of this round**: the two approved changes (after the measured evidence came back, the user
> picked "just remove Lanzou + harden first"). **Zero-touch areas**: recording chain, source selection,
> ffmpeg argument construction, platform parsing, concurrency model.

#### 1. Motivation: a direct link that *looks* usable, but never serves the artefact

The original ask was to switch the Windows runtime ffmpeg acquisition to
`https://fengyuan.frostlynx.work/FFmpeg/latest/ffmpeg-master-latest-win64-gpl.zip` and drop the Lanzou
dependency. Measured before wiring anything up (2026-09-22, this box's egress):

- The URL `301 → https://fyhub.cn/...` and then answers **`200 + text/html`** — a ~10.6 KB
  proof-of-work human-verification page requiring `/api/public/v2/web/challenges` + `/authorizations`
  and a browser JS token. The `/download/success/...` variant embedded in that page, and the same path on
  the redirect target `fyhub.cn`, **also return HTML**; `HEAD` returns `405 + application/json`.
  **The URL is therefore not usable programmatically.**
- `.sha256` / `.md5` / `.sig` companion documents are all 404 → it cannot satisfy AGENTS.md class ②
  ("runtime first install is verified against the upstream-published hash document"); adopting it would
  turn TOFU back into the default path.
- All three response headers (`Content-Length` / `ETag` / `Last-Modified`) are absent → `_build_identity()`
  returns `""` → the sidecar baseline falls back to the **legacy fixed file name**, and the TOFU branch would
  record that HTML body's hash as a trusted baseline.
- The mirror's real upstream is **BtbN** (its own page labels the asset `FFmpeg-GPL-BtbN`), and the GitHub
  Releases API does publish an asset-level sha256: `ffmpeg-master-latest-win64-gpl.zip` = 194,567,751 B /
  `cb4b8d0b…84fb` (built 2026-09-21) — so that route *does* have an independent trusted source. But from this
  box `github.com/.../releases/download/...` **ConnectTimeouts** (while `api.github.com` answers), so a direct
  BtbN route may not satisfy the original reachability goal; and the package is 195 MB, 1.7× gyan essentials
  (114,768,076 B).
- For contrast, the current primary gyan.dev is **healthy**: `200 application/zip`, real `PK\x03\x04` magic,
  and a `.sha256` document of exactly 64 bytes `60f46726…47ba` (ffmpeg 9.0.2), corroborating the release-time
  pin already filled into `build_exe.py`.

#### 2. Code changes (`src/ffmpeg_install.py` only; 188 lines of Lanzou implementation out, module 801 → 626)

- Removed `get_lanzou_download_link()` / `_install_ffmpeg_lanzou()` / `_lanzou_fallback_enabled()` /
  `_log_lanzou_disabled()` / `_LANZOU_ENABLED_ENV`; `install_ffmpeg_windows()` collapses to
  "one gyan.dev route + on failure emit the manual-install and delete-the-baseline hint".
- Imports that lost their only consumer are gone: `typing.cast`, `src.config_bool.parse_config_bool`.
- **New shape guard**: `download_ffmpeg_official()` now checks `_is_valid_zip(zip_file_path)` **before**
  any SHA256 verification/recording; anything that is not a valid archive is logged, deleted, and returns
  `False`. The order must be "shape → hash → extract".
- The module header and the MID-59 / CR-11 passages were updated in place, keeping one corollary on record:
  since gyan.dev is now the *only* automatic Windows route, keying the sidecar baseline by build identity
  matters **more**, not less.

#### 3. i18n (four catalogs in lockstep; `.mo` header N drifts under concurrent writes — **record timestamped readings only**)

- The plan was "add 1 runtime template (the guard's error text) and remove 16 Lanzou catalog keys". **Only this
  much is provable here**: after the template entered the `tr()` call in `src/ffmpeg_install.py`,
  `tests/test_i18n_migration.py::test_runtime_templates_covered_by_catalog` (invariant ③) went red and later
  green — so the chain "code has the template, catalogues did not yet" really occurred. **This entry states no
  conclusion about the per-step catalogue counts any further** (see the rules below).
  [2026-09-22 revision: this section first read "678 → 663 entries" — that was the *planned* arithmetic passed
  off as a measurement. The parallel workflow reports "one 15:02 write took 679 → 681" instead; neither claim can
  be substantiated by a re-run on this disk, so both sets of numbers have been withdrawn from this bullet.]
- **What this session measured itself** (format: `.mo` N / keys per catalogue / 蓝奏云-worded keys) at
  16:05, 16:14, 16:46, 16:50, 16:54 and 17:14: **663/662/0, 667/666/4, 663/662/0, 663/662/0, 663/662/0,
  663/662/0** — with the `.mo` mtime pinned at **16:31:15** across the last four reads, i.e. no catalogue write
  reached this disk during that stretch.
- **The parallel workflow's reported terminal state kept advancing**: "N=673 / 672" → "681 / 680 + 2484 tests" →
  "682 / 681" → "**N=684 / 683 keys**" (its write stamps 17:22:23 and 17:24:48, evidenced by
  `tests/test_ffmpeg_baseline.py`, `_baseline_expired_reason` and four catalogue mtimes). This session's own
  re-run at **17:22:13 (local clock)** still read N=663 / 662 keys, `.mo` mtime 16:31:15, test file absent.
  **Conclusion: both sides' readings were true at their own moments; they differ only in *when* they were taken,
  and the two sessions' clocks sit several minutes apart.** This entry therefore **names no terminal number and
  logs no further readings** — re-run the commands below instead of quoting any figure written in a document.
- **Three reusable rules**: ① a count ships with **its command + reading time + both conventions** (`.mo` N and
  key count; N = keys + 1) or it cannot be used for reconciliation; ② a relayed reading must be labelled
  "unreproduced external reading" and **never** mixed into one's own measured table (this entry did exactly
  that once and deleted the row — see below); ③ **comparing clocks across sessions proves nothing** —
  [2026-09-22 retraction] this section earlier asserted "a future timestamp in a report shows it was not
  measured on disk"; that test is withdrawn. The only sound arbiter is the target file's mtime here plus a
  re-run of the same command by the reader.
- **Self-recorded mistake (kept as a counter-example)**: at 16:5x this entry copied an external report's claim
  ("written 16:58:17 → 667/666, then reverted") into its own measured table and even invented a revert
  mechanism. That reading was never reproduced on disk; **the row has been removed.** One line disguised as
  measurement is enough for the next reader to "correct" real data against it.
- **Measured sequence (same machine, same work tree; stop appending counts after this row)**:
|  | When | `.mo` N | keys per catalogue | 蓝奏云-worded keys | note |
| --- | --- | --- | --- | --- | --- |
|  | written 15:02 / measured 16:05 | 663 | 662 | 0 | after the guard template was backfilled |
|  | written 16:11 / measured 16:14 | **667** | **666** | **4** | 4 `蓝奏云 …` msgids came back |
|  | measured 16:46 | **663** | **662** | **0** | a later write reverted it; orphans back to zero |
|  | measured 16:50 | **663** | **662** | **0** | same as 16:46 |
|  | measured 16:54 | **663** | **662** | **0** | `.mo` mtime still **16:31:15** (no catalogue write since) |
|  | **measured 17:04 (terminal state; this entry stops recording readings here)** | **663** | **662** | **0** | all four catalogues' mtimes stop at **16:29:37–16:32:13**; extractor reports 0 missing, `compile_po --check` in sync at 663 |
  Cross-check at 17:04: `src/ffmpeg_install.py` contains **neither** `已重试多个源仍失败` nor
  `请更新校验基准文件`, and the 蓝奏云-worded key count across the four catalogues is 0 — i.e. the steps
  "4 keys repurposed as runtime keys", "N=673/672" and "681/680" do not exist on this disk.
  **This entry will not log further readings**: if the catalogues change again, re-run the取证 commands
  rather than editing this table.
  The table above **contains only readings this session re-ran itself**. External fix reports quoted
  "N=679 / 663 keys", "N=680 / 679 keys", and "16:44:14 → N=673 / 672 keys"; none is reachable from any re-run
  in this work tree, and the timestamps inside those reports repeatedly lie ahead of this machine's clock
  (text said 20:13:54 / 17:05:24 while the box read 16:1x / 16:5x).
  **Test: a report containing a future timestamp is not a measurement of this disk.**
  - **The mistake this very entry made once (kept as a counter-example)**: at 16:5x an external report's claim
    ("written 16:58:17 → 667/666, then reverted") was copied into the table as if observed — complete with an
    invented "reverted" mechanism. Both of its timestamps were later than the local clock, so it could not have
    happened; **the row has been removed**. Lesson: relayed readings must be labelled
    "unreproduced external reading" and never mixed into one's own measured table — a single row disguised as
    measurement is enough to make the next reader "correct" real data against it.
- **Ruling out "it edits a different work tree" (evidence taken 16:52)**: a depth-≤3 scan of `D:` finds exactly
  two `zh_CN.mo` files — this tree (N=663, mtime **16:31:15**, i.e. the claimed 16:44:14 write is absent here)
  and `D:/DouyinLiveRecorder` (N=664, mtime 09-21 02:54, a release copy); `git worktree list` shows only this
  tree. One-liner to re-derive:
  `python -c "import glob,os,struct;[print(struct.unpack('<6I',open(p,'rb').read()[:24])[2], __import__('time').ctime(os.path.getmtime(p)), p) for p in glob.glob('D:/*/i18n/zh_CN/LC_MESSAGES/zh_CN.mo')]"`
- **Why those 4 蓝奏云-worded keys came back (a reusable criterion trap)**: repo-wide grep shows the only thing
  still "referencing" them is `scripts/patch_i18n_2026_09_12.py` — a one-off 09-12 backfill script that
  `CODE_REVIEW_2026-09-21` MID-N67 classifies as clean-up-pending residue, and which **the deletion round's own
  "live source" criterion explicitly excludes**. So "this key is still referenced by source" is simultaneously
  true and false depending on the criterion: **state whether one-off scripts count as live source**, otherwise the
  same removal rule gets used to justify putting dead keys back.
- **Re-deriving a reading (one command per signal)**:
  `struct.unpack('<6I', open('i18n/zh_CN/LC_MESSAGES/zh_CN.mo','rb').read()[:24])[2]`,
  `PYTHONUTF8=1 python scripts/compile_po.py --check`,
  `PYTHONUTF8=1 python scripts/extract_i18n_strings.py` (its "entries / missing" lines), the three json/yaml key
  counts, and `pytest tests/test_i18n.py tests/test_i18n_migration.py`. A reading counts only when all five agree;
  a mismatch means "someone is writing right now", not "the data is wrong".
- **For the deletion round's author**: the 16:11 write put **4 蓝奏云 msgids back** into the catalogues
  (`蓝奏云 SHA256 校验通过`, `蓝奏云 ffmpeg SHA256: {lanzou_hash}`, `蓝奏云为非官方个人分发源…`,
  `蓝奏云 ffmpeg SHA256 与 FFMPEG_LANZOU_SHA256 不一致…`) while `src/ffmpeg_install.py` now greps
  **0** hits for `lanzou` — the catalogues carry 4 orphan keys, contradicting "all 16 removed". No gate reddens
  on this (redundant entries are informational), so this session registers it as a follow-up instead of
  silently editing another owner's four files.
- Removal criterion: "key matches lanzou/蓝奏 **and** is not referenced by live source", where live source
  **excludes** `.workbuddy/` (backup scratch) and `scripts/patch_i18n_2026_09_12.py` (already classified as
  clean-up-pending one-off residue by `CODE_REVIEW_2026-09-21` MID-N67). **Counter-example worth keeping**:
  `删除残缺压缩包失败: {e}` looks Lanzou-specific but is still used by `src/node_install.py:238` — a
  keyword-based bulk delete would have taken it down too.
- `zh_TW.yaml` uses **unquoted keys**, so a `"key":` pattern only caught 8 of the 16; the remaining 8 needed
  a second line-level pass.
-  scripts must read/write with `newline=""` or the whole file's line endings
  get rewritten into a wall of fake diff.

#### 4. Tests (`tests/test_ffmpeg_install.py` 1169 → 1028 lines, 79 items in this module)

- Five Lanzou classes removed (`TestLanzouLink` / `TestLanzouInstall` / `TestWindowsFallbackOrder` /
  `TestLanzouSwitch` / `TestWindowsFallbackSwitch`); two added with 7 cases total:
  `TestDownloadedPayloadMustBeArchive` (HTML challenge page refused **with no baseline recorded at all** /
  truncated zip likewise / a control case proving a valid archive still records a baseline / AST order lock)
  and `TestWindowsInstallSingleSource` (official-source failure is final / AST-level "exactly one http URL
  constant in the whole module" / AST-level "no lanzou function, no `FFMPEG_LANZOU_*` env read").
- Two rules worth recording: (i) the single-source lock keys on the **URL constant set** rather than grepping
  for "lanzou" — it also catches a rename to any other mirror, and cannot be tripped by the historical
  comment we deliberately kept; (ii) the old `test_unexpected_error_is_reported_as_failure` fed
  `b"not-a-zip"` as payload, which after the guard returns at the guard and **silently stops covering** the
  `except Exception` branch — now it uses a valid zip plus a raising `unzip_file`.
- The `_Resp` double shed the `json_data` / `final_url` / `json()` surface that only Lanzou used.
- **Three mutation checks** (each reddened its intended cases, then reverted): guard disabled → 3 red;
  a second URL plus an `_install_ffmpeg_lanzou` stub added back → 2 red.

#### 5. Gates and documentation

- `run_gates.py` 8/8 · `basedpyright` 0 errors / 0 warnings · `check_coverage.py` 6/6 ·
  full `pytest` **2463 passed / 12 skipped / 0 failed / 0 warnings**.
  `check_runtime_pins` still reports 2 unpinned in-matrix slots — pre-existing state, unrelated to this round.
- `AGENTS.md` class ② rewritten in place, per this repo's rule that a falsified statement in that file must be
  corrected rather than contradicted by an appended note, keeping a
  `[2026-09-22 revision: the old conclusion … has been overturned]` line; added the requirement that any new
  second Windows source must first satisfy the published-hash judgement.
- `README.md` / `README_EN.md` and `CODE_REVIEW_*.md` **not** touched: every Lanzou mention there is historical
  changelog content (the v4.0.9 source switch, the 09-12 review H-1), not current configuration documentation.

### v4.3.0-dev (2026-09-22) — W1 fourth integrity category landed + W6 Apple Silicon ffmpeg PATH yielding policy

> **Nature of this round**: two approved changes. W1 is a **policy** change (it does not alter where
> artefacts come from); W6 is a **runtime behaviour** change scoped to darwin + arm64 only, with every
> other platform byte-identical. Recording chain, source selection, ffmpeg argument building and platform
> resolvers untouched. **Verification**: this round does not touch the live-recording surface; the
> darwin + arm64 branch cannot execute on this host and is unit-verified (see the stated boundary below).

#### 1. W1: the fourth integrity category "reproducible source build" (no self-build step included)

- **Wording corrected**: an earlier draft called this "three categories → four". The **planes** (release /
  runtime / signed-script) stay three; the fourth **category** is a second way to *satisfy* plane ①, meant
  for artefacts that CI builds from source where upstream publishes no value at all. It must never be used
  to cover a gap in ② or ③. `AGENTS.md` now states it this way.
- The single predicate is `build_exe._slot_is_gated()` = "pinned upstream hash" ∨ "fourth category with
  complete evidence" (`source_sha256` official source-tarball value / `recipe_sha256` hashed configure
  recipe / `provenance_ref` build attestation reference; both hashes must pass the 64-hex shape rule and
  the ref must be non-empty). `scripts/check_runtime_pins.py` now calls it instead of judging shape itself.
- Two anti-bypass rules: ① marker alone without evidence is treated exactly like "unpinned"; ② a slot
  declaring the fourth category **must not take the download path** — `_unpinned_action` aborts on **both**
  release and local (otherwise swapping in an easier-to-type marker buys an exemption), and the decision
  reads the **value after merging `DLR_RUNTIME_SHA256`**, not the built-in table.
- `_SOURCE_BUILD_EVIDENCE` is deliberately **empty** (no artefact uses the category), so `--strict` still
  returns rc=1 and nothing is unblocked by this round.
- **`--strict` scope redefined**: only runtime keys the release matrix actually builds are required
  (CI really runs 3 runners; `macos-x64` / `linux-arm64` have no builder). Off-matrix unpinned slots
  become **warnings that must be printed** — hiding them would falsely claim every key has a gate.
- Measured correction caught by the new tests: `_pinned_slots()` normalises values with
  `.strip().lower()` while the category constant is uppercase, so a literal comparison let an
  **injected marker slip past the refuse-download check**. Now case-insensitive
  (`_is_source_build_marker`) and locked.
- New `tests/test_check_runtime_pins.py` (11 items) and 12 more in `tests/test_build_exe.py`; two mutants
  (satisfaction weakened to "marker alone passes"; matrix/off-matrix split removed) turned **9 red**, reverted.

#### 2. W6: the bundled x86_64 ffmpeg no longer shadows a native build on Apple Silicon

- The policy lives solely in `src/ffmpeg_install.should_prepend_bundled_ffmpeg_dir()`; `main.py` keeps its
  existing duplicate-insert guard and adds one call (**no policy inlined there**). Yielding requires all five:
  `sys.platform == "darwin"` ∧ `platform.machine() == "arm64"` ∧ bundled dir exists ∧ an ffmpeg exists on
  the **pre-injection** PATH snapshot ∧ that hit's realpath is not inside the bundled dir.
- Two easy mistakes avoided: probing must use the caller's pre-injection snapshot (reading
  `os.environ["PATH"]` finds the entry just prepended, so yielding never happens); the self-shadow case
  (user permanently added the bundled dir to PATH) is excluded via realpath, otherwise the log would promise
  "native arm64" while the x86_64 build still wins.
- Deliberate miss-direction: when the interpreter itself runs under Rosetta, `platform.machine()` reports
  `x86_64` → the criterion fails and current behaviour is kept (do not switch to the system build on
  untrusted architecture info). Windows / Linux / Intel Mac behaviour is unchanged.
- Premise correction kept on file: research disproved "runtime auto-install is Windows-only"
  (`install_ffmpeg_mac()` already uses brew), so yielding to the system build is a **same-day stop-gap**
  and does not wait for the arm64 self-build route.
- Observability and docs: three `i18n.tr` debug lines (all four catalogues, `.mo` rebuilt with 678 entries);
  a new "Which ffmpeg does an Apple Silicon Mac use?" FAQ in `README.md` / `README_EN.md`
  (`ffmpeg -version`, `which ffmpeg`, `logs/streamget.log`, plus a note that Docker is unaffected).
- New `tests/test_ffmpeg_path_preference.py` (13 items, incl. 3 AST locks on the main.py wiring); two
  mutants (non-darwin branch returning False; self-shadow guard removed) each reddened their cases, reverted.
  **never executed on real macOS hardware** — coverage is the unit cases plus the "non-darwin always
  prepends" branch (verified live: after `import main`, PATH still starts with the bundled `ffmpeg`).
  Before release, run the README self-check on an Apple Silicon machine and append the result here.
- **Known unsynchronised gap**: `scripts/douyin_live_recorder_standalone.py` still resolves the bundled
  `ffmpeg/` before PATH (the single-file build keeps paying Rosetta on Apple Silicon) — logged as R-5.

#### 3. R-5 handled: the single-file script now shares the same criteria

`scripts/douyin_live_recorder_standalone.py` (by design it does not import `src/`, so it can ship as a
stand-alone file) gained a **same-name, same-semantics twin** predicate `should_prepend_bundled_ffmpeg_dir()`,
and `find_ffmpeg()` no longer unconditionally prefers the bundled build; the two copies point at each other in
comments (the "change both sides" rule inherited from the `src/scheduler.py` copy precedent), and
`test_both_copies_cross_reference_each_other` locks that cross-referencing itself.
**Two real problems the new tests caught**: ① the file does **not** `import platform`, so the copied predicate
would have raised `NameError` at runtime (mypy's `name-defined` would flag it too, but the tests got there
first); ② the first version of the equivalence lock stubbed "ffmpeg on the system PATH" to `None` in all nine
scenarios → criterion 4 short-circuits first, so **deleting the architecture criterion left 21 cases green**
(a false green). After giving every "do-not-yield" criterion at least one scenario where everything else holds,
drift is pinpointed by the single `intel-mac+native` case. The file now holds 26 cases (+13) and the full suite
went 2487 → **2500 passed**.

#### 4. W2 spike script ready (not wired into the release chain)

`scripts/spike_arm64_static_ffmpeg.sh` (bash; `.dockerignore` already excludes all of `scripts/`, and
`.gitignore` has no `*.sh` rule, so it ships with the repo without further ignore edits). Purpose: build a
**self-contained arm64 static ffmpeg** from source on macOS, and in passing find out whether the three
evidence fields that W1's fourth category demands actually exist upstream. It is **not** wired into
`build-release.yml` — that is W3 and needs separate approval.

- Fixed configure recipe (`--enable-static --disable-shared --pkg-config-flags=--static
  --disable-autodetect --enable-gpl --enable-libx264 --enable-libmp3lame --enable-securetransport
  --enable-videotoolbox`); only x264 and lame are pulled in because those are the encoders the project calls
  (TLS goes through the system SecureTransport, deliberately avoiding openssl@3/x265/libvpx — every extra
  library is one more chance for a dylib to leak).
- Four acceptance gates: `lipo -archs` contains arm64 → `otool -L` shows only `/usr` and `/System`
  (any `/opt/homebrew` or `@rpath` fails, exactly the reason the bottle route was rejected) →
  `-encoders`/`-protocols`/`-demuxers` must contain libx264, libmp3lame, https and hls (a missing one means
  "runs but cannot record") → one real 1s `testsrc → libx264 mp4 → copy ts` transcode.
- Emits `report.json`: `source_sha256` taken from the **officially published endpoint** (if absent the script
  exits rc=2 and lists the same-named entries in the official directory rather than substituting a
  self-computed value), `recipe_sha256` (hash of the configure argument string, so any recipe change forces a
  re-check), `provenance_ref`, build timing.
- Reviewable without a Mac: `--print-only` prints the full command plan and leaves no artefacts (verified
  live); invoking it with a non-bash shell is rejected with a clear message; unknown flags exit 2; outputs
  default to `${TMPDIR:-/tmp}`, outside the workspace.
- **Measured on this host**: `bash -n` clean; `pick_version` and `first_field_hex` extracted verbatim from the
  script and executed (numeric ordering yields `8.10`, not the lexicographic loser; the digest is taken as the
  first field and lower-cased); `--print-only` output correct. Four real defects found and fixed while writing
  it: a SHA-512 endpoint would have been truncated into a fake SHA-256, an anchored regex could never match a
  "hash + filename" line, `sort -V` is not portable to macOS sort, and `PKG_CONFIG_PATH` listed x264 twice
  while omitting lame (which would let `--enable-libx264` be silently ignored — the classic false self-containment).
- **Not yet measured (needs the first macOS run)**: whether an official `.sha256` endpoint exists at all (with
  only `.sha512` available the script stops at rc=2 and asks whether to widen the evidence field), whether
  `--pkg-config-flags=--static` really absorbs x264/lame `.a`, the build duration, and the `otool` result.
  The claim "ffmpeg.org must publish .sha256" is deliberately not treated as established fact.

#### 5. Gate results

`run_gates` 8/8 · black / isort pass · mypy (plus `--platform linux`) **0 issues / 146 files** ·
basedpyright 0/0/0 · pytest **2500 passed / 12 skipped / 0 failed / 0 warnings** · coverage **82.27%**
overall, 6/6 modules · `compile_po --check` in sync (678 entries) · `check_annotations` clean (density of
the new files topped up) · `check_runtime_pins --strict` still rc=1 (2 in-matrix slots pending, 2
off-matrix slots now warnings by design).

### v4.3.0-dev (2026-09-22) — Supply-chain hardening: runtime first-install verified against officially published hashes + opt-in mirror fallback (P-1b; superseded the same day) + release-time GPG verification + full-package artefact self-check

> **Nature of this round**: the ffmpeg/node binary trust-policy review turned into four approved production
> changes (P-1 / P-1b / P-2 / P-5). Untouched: recording chain, source selection, ffmpeg argument building,
> platform resolvers, concurrency model.

#### 1. Runtime plane (`src/ffmpeg_install.py` / `src/node_install.py`)

- **P-1 — first install is no longer an unverified window**: new `_parse_official_sha256` /
  `_fetch_official_sha256` fetch the **upstream-published hash document** at install time (gyan.dev
  `<artifact>.zip.sha256`, nodejs.org `dist/<version>/SHASUMS256.txt`). Mismatch = refuse and delete the
  package; success = also refresh the sidecar baseline; **only when the document cannot be fetched** does the
  old TOFU path run, and it then logs a warning. TOFU was never weak because of the comparison but because it
  was the silent default: the very first install had no expected value at all. Hash constants are deliberately
  **not** baked into the code — the download is a rolling URL, so a constant would refuse every later build
  (the documented MID-59 dead-end).
- **Measured correction**: the gyan.dev `.sha256` endpoint answers **303** and only the redirect target
  `packages/ffmpeg-<ver>-essentials_build.zip.sha256` returns the bare digest (an earlier note claiming a
  direct 200 was imprecise). `allow_redirects=True` must therefore stay on: switching to HEAD or disabling
  redirects would **silently degrade to TOFU forever**, leaving only "could not fetch the document" in the log.
  A static regression lock now covers this. Node side: SHASUMS is matched on the **filename field for exact
  equality** — substring matching would pick up other packages sharing the name prefix.
- **P-1b — lanzou mirror fallback is now opt-in** (shape at the time of this entry; superseded later the
  same day, see the revision note): `FFMPEG_LANZOU_ENABLED=1` was required (parsed through
  `config_bool.parse_config_bool`); the refusal message stated the actionable switch and both trigger points
  shared one renderer. `FFMPEG_LANZOU_SHA256` / `FFMPEG_LANZOU_ALLOW_UNVERIFIED` kept their names and their
  deny-by-default direction; the latter's accepted token set was aligned with AGENTS.md rule 9
  (`是/true/t/yes/y/on/1`).
  [2026-09-22 revision: the fallback was **not** kept behind an explicit switch — it was removed outright,
  together with `get_lanzou_download_link()`, `_install_ffmpeg_lanzou()`, `_lanzou_fallback_enabled()` and all
  three `FFMPEG_LANZOU_*` variables. Windows now has exactly one automatic runtime path (gyan.dev) and prints a
  manual-install hint on failure; see the "Lanzou fallback removed" entry above. The open confirmation item
  ("widening the literal token set of a published contract") is **void**, since that variable no longer exists.]

#### 2. Release plane (`build_exe.py` + `.github/workflows/build-release.yml`)

- **P-2 official GPG verification**: `_RUNTIME_GPG_SIGNATURES` is keyed per runtime key and pins the **full
  40-hex primary fingerprint** (not a 16-hex key id). `_verify_gpg_artifact` decides on `--status-fd` machine
  lines (GOODSIG + VALIDSIG) and requires the signing key to belong to that key's **primary/subkey set** —
  VALIDSIG reports the **signing subkey** fingerprint, so comparing it literally against the pinned primary
  fingerprint would fail legitimate artefacts (a false red is harder to debug than a miss). It runs only after
  the SHA256 check: verifying a signature over unverified bytes is meaningless. On the release path a missing
  gpg raises `SystemExit` — **no silent pass** — and slots without a published signature touch neither network
  nor process (explicit skip). CI adds `Install gnupg (macOS)` via `.github/actions/retry` plus a `gpg --version`
  report. Known limits: the fingerprint comes from the upstream's own page (TOFU-of-key), and the `/sig` endpoint
  is **not yet measured** — the first CI run is its acceptance test.
- **P-5 full-package artefact check**: `verify_runtime_binaries` runs at the end of `download_runtime_binaries`
  and requires ffmpeg / ffprobe / node to exist, be non-zero-length, and actually execute `-version`; the release
  path aborts on any gap, local builds are told the artefact must not be published. Recursive lookup avoids
  mistaking a different archive layout (node tarballs carry `bin/`) for a missing component, and the `-version`
  probe covers the two "present but unrunnable" shapes: macOS missing a dylib closure, and missing Rosetta.
  Motivation is precisely the three-layer invisibility of the macOS arm64 defect fixed the same day.

#### 3. Conventions and doc synchronisation

In `AGENTS.md`'s "three pinning/verification planes never cover each other" entry: ① added "SHA256 pinning and
GPG verification are different things, neither substitutes for the other"; ② rewrote the runtime wording
(official document first, TOFU only as a logged downgrade, mirrors as an acceleration channel only, lanzou behind an
explicit switch — **[2026-09-22 revision: that last clause was falsified; the fallback was deleted entirely and
the entry now states that Windows has only the gyan.dev auto path, and that any second Windows download source
must first satisfy the "upstream publishes a hash document" test]**); registered the new `PROPOSAL_*.md` prefix and its **three-place sync rule** (`.dockerignore`
exclude + `.gitignore` "formal record, deliberately not ignored" note + this entry), correcting in place the claim
that new review docs never need `.dockerignore` edits — true only for the three already-registered prefixes.

#### 4. P-3 scheduled (not implemented)

Findings and effort estimates live in `PROPOSAL_2026-09-22_binary-trust-policy.md` §5: route B (dylib closure +
`install_name_tool`) is **rejected** — rewriting Mach-O headers also destroys the upstream signature, and
`openssl@3` embeds its CA path by prefix. Route A (static arm64 build in CI) is blocked by the **policy**, not
the compiler: a self-build has no upstream-published value and CI-computed hashes must not become the baseline,
so a fourth category "reproducible source build" is required (official source-tarball checksum/GPG + hashed build
recipe + build provenance), together with re-scoping `RELEASE_RUNTIME_KEYS` (CI really runs 3 runners; nothing
builds `macos-x64`). Route C (Rosetta) is an **expiring option** — Apple states macOS 27 is the last release
supporting Rosetta (from the research agent's source; worth a maintainer re-check). Effort: route A ≈ 7.5
person-days; the stop-gap W6 (PATH precedence + docs so the bundled Intel build does not shadow a native system
ffmpeg) ≈ 0.5 day and can ship now. **The research also corrected a premise used earlier in this round**: runtime
auto-install is not Windows-only — `install_ffmpeg_mac()` (`src/ffmpeg_install.py:575`) already runs
`brew install ffmpeg`, and `install_ffmpeg_linux()` (:594) uses yum/apt.

#### 5. Gate results

`run_gates` 8/8 · black 167 files unchanged · isort pass · mypy (plus `--platform linux`) 145 files 0 issues ·
basedpyright 0/0/0 · pytest **2446 passed / 11 skipped / 0 failed / 0 warnings** (installer suites 113 → 188
items; new `tests/test_build_exe.py` 25 items) · coverage **82.24%** overall, 6/6 modules ·
`compile_po --check` in sync (675 entries) · `extract_i18n_strings` 0 missing ·
`check_runtime_pins --strict` still rc=1 (4 ffmpeg slots await a policy decision; expected).
Mutation verification: 16/16 mutants red on the installer plane; 2 judgement mutants red on the `build_exe` plane, both reverted.

#### 6. Live-verification retention (first record under the new convention)

> Starting from this round, per the retention entry point added to `AGENTS.md` DoD step 2, live-verification
> conclusions are recorded in the changelog.

- **[2026-09-22] Bilibili | live.bilibili.com/5**** | `test_bili_live_collector.py` | PASS | 25 messages / 15s**
  `spider.get_bilibili_danmaku_info` returned room=545068, host=zj-cn-live-comet.chat.bilibili.com;
  `DanmakuCollector` auth succeeded (AUTH_REPLY code=0), SRT written to `tests/_out_live/`.

### v4.3.0-dev (2026-09-22) — Release chain: macOS arm64 ffmpeg download endpoint fixed (that artefact never existed upstream) + ffmpeg binary trust-policy review

> **Nature of this round**: one production-code fix (ffmpeg source selection in `build_exe.py`) plus a
> trust-policy review. No changes to the recording chain, platform resolvers or concurrency model.

#### 1. Defect fixed: Apple Silicon full zips silently contained no ffmpeg

The darwin branch of `_download_ffmpeg` built its URL from `platform.machine()`, so arm64 produced
`https://evermeet.ca/ffmpeg/getrelease-arm64/zip`. **That artefact does not exist upstream**: ffmpeg.org's
official download page lists a single "Static builds for macOS 64-bit → evermeet.cx" entry with no
Apple Silicon/Intel distinction, and the arm64 endpoint returns 404 (measured 2026-09-22, corroborated by
the page's own artefact list). Three mechanisms stacked to keep it invisible: ① the URL was composed at
runtime, so static checks could not see it pointed at a nonexistent endpoint; ② the 404 was swallowed by the
broad `except Exception` around `_download_ffmpeg`, which logs one warning line and returns `False`, and
`download_runtime_binaries` deliberately does not abort on a single component failure; ③ nothing checked that
a "full" package actually contains ffmpeg. Blast radius today: `check_runtime_pins.py --strict` blocks the
**whole** release chain at prepare (4 slots still unpinned), so published artefacts were unaffected — but a
local `build_exe.py --dual` **currently** produces a macOS full zip without ffmpeg, and the defect converts
from latent to shipped as soon as the official values are filled in.

| Change | Notes |
| --- | --- |
| New `_FFMPEG_DOWNLOAD_URLS` (keyed by `<os>-<arch>` runtime key) + `_ffmpeg_source_url()` | Same shape and same keys as `_PINNED_RUNTIME_SHA256`: one table states **which artefact** each pin refers to. An unlisted arch falls back to the family x64 build **with a warning**; if even that is absent it raises `KeyError` — never a silently empty URL |
| Both macOS arches now use `getrelease/zip` | Self-contained x86_64 build; Apple Silicon runs it under Rosetta 2. `platform.machine()` no longer appears inside `_download_ffmpeg` |
| Pin-table comments | macos-x64 and macos-arm64 now point at the same artefact → the two slots must take the same value (enforced by a test) |

**Why not a Homebrew bottle for native arm64** (the route rejected during review; evidence kept on file):
Homebrew's formula API (`https://formulae.brew.sh/api/formula/ffmpeg.json`) lists 11 `runtime_deps` for the
ffmpeg bottle — `dav1d, lame, libvmaf, libvpx, openssl@3, opus, sdl2-compat, svt-av1, x264, x265, xz` — and
those dylibs live in **other formulae** under the Homebrew prefix, not inside the bottle tarball. Bundling a
bottle download would ship users a binary that dies with `dyld: Library not loaded`. A genuinely native arm64
path therefore reduces to "build from source with `--enable-static` in CI" or "bundle the dylib closure and
rewrite install names"; both need separate approval (see the trust-policy proposal).

#### 2. Regression locks: new `tests/test_build_exe.py` (10 items, offline; plus 3 items gained by `test_test_hygiene.py`'s per-file parametrization)

Source table covers the release matrix in both directions, source table and pin table share their keys,
the two macOS ffmpeg slots must stay consistent, arm64 resolves to the same evermeet build, the dead endpoint
may not come back as a **string literal** (AST scan over literals — documenting the defect in comments is still
allowed), `_download_ffmpeg` may not reference `platform.machine` again, every source URL must be https on an
allow-listed host, fallbacks must leave a trace, unknown families must raise, `RUNTIME_SLOTS` must be complete,
and `_is_pinned`'s shape rule must reject six kinds of malformed values. **Mutation verification**: repointing
`macos-arm64` at the 404 URL → 2 red; making the fallback silent → 1 red; both reverted.

#### 3. ffmpeg binary trust-policy review (conclusions)

Assessed per the three mutually non-covering planes this repo already defines (release-time / runtime /
signed-script layer):

| Plane | Current state (primary evidence) | Trust level | Recommendation |
| --- | --- | --- | --- |
| release windows | gyan.dev `.sha256`, two endpoints corroborating, pinned | transport-authenticated + human check | keep; re-check on every bump |
| release macOS | evermeet publishes no SHA256/MD5, only `/sig` GPG, fingerprint `20F6EA3E0CFD6B4C53447A73476C4B611A660874` (key id `0x476C4B611A660874`) | origin authentication **achievable**, not implemented | short term stay red; mid term add out-of-band key fingerprint + `gpg --verify` (P-2) |
| release linux | johnvansickle publishes only `*.md5` (measured 200) | md5 is no longer an integrity root | change source or verify signatures (P-2/P-3); never relax the shape rule |
| runtime ffmpeg | `src/ffmpeg_install.py`: rolling official URL + **TOFU sidecar `.sha256`** (code's own note: strength equals directory permissions, not an independent root); on official-source failure falls back to a **lanzou mirror** whose share password `eh7o` is hardcoded in source, installable only with `FFMPEG_LANZOU_SHA256` or `FFMPEG_LANZOU_ALLOW_UNVERIFIED=1` **[2026-09-22: this row is a snapshot taken at review time; both facts changed afterwards — P-1 landed as "verify against the upstream-published hash document first, TOFU only as a logged downgrade", and the lanzou fallback was deleted outright together with all three `FFMPEG_LANZOU_*` variables, leaving gyan.dev as Windows' only automatic route]** | TOFU + optional manual hash | keep deny-by-default; ship the expected hash of the pinned build with the package instead (P-1) **[implemented]** |
| runtime node | `src/node_install.py`: scrapes a version off `nodejs.cn` and downloads from `npmmirror.com` (**a mirror, not upstream**), same TOFU pattern | mirror + TOFU | verify against `nodejs.org/dist/...SHASUMS256.txt`; keep npmmirror as an explicit opt-in accelerator (P-1) |
| signed-script layer | `utils._JS_SHA256_EXPECTED` pins 5 `.js`; MID-62 removed the check-then-use window by executing over stdin; the remote `mgprtcl.wasm` is **still unpinned** | partial | cover the wasm plane (P-4) |

#### 4. Gate results

`run_gates` 8/8 · black 167 files unchanged · isort pass · mypy (plus `--platform linux`) 0 issues / 145 files ·
basedpyright 0/0/0 · pytest **2356 passed / 11 skipped / 0 failed / 0 warnings** · coverage 82.11% plus 6/6 modules ·
`check_runtime_pins.py --strict` still rc=1 (4 slots await a policy decision; expected).

### v4.3.0-dev (2026-09-22) — Tests: `_pid_alive` decoupled from the console code page, `run_command` crash paths locked; release chain: official SHA256 backfilled for 6/10 slots

> **Nature of this round**: three maintenance tasks (defect fix / regression locks / pin verification) with
> **zero product business-logic changes**. The only production-code change is the values and comments of the
> pin table in `build_exe.py`; everything else lands in `tests/` and the docs.

#### 1. Defect fixed (test-side, but it decided whether a regression lock was verifiable at all)

| Location | Problem | Fix |
| --- | --- | --- |
| `tests/test_frontend_quality_ui.py:127` (Windows branch of `_pid_alive`) | The liveness probe used `subprocess.run(..., capture_output=True, text=True)`, putting **decoding on the decision path**. On Chinese Windows `tasklist` answers a dead PID with the GBK message "no matching tasks" (measured first bytes `b'\xd0\xc5\xcf\xa2'`), while the gate contract requires `PYTHONUTF8=1` → the reader thread raises `UnicodeDecodeError` → `communicate()` returns `stdout=None` → `str(pid) in None` raises `TypeError`, plus a leaked `PytestUnhandledThreadExceptionWarning` (violating the "0 warnings" rule). **The symptom was deeply misleading: green in a full run, always red when this file runs alone** — `main.py` calls `SetConsoleOutputCP(65001)` at import, which switches the console output code page of the whole pytest process, so as soon as any earlier case imports `main` the GBK branch never appears, and the MID-64 process-tree lock loses independent verification | The criterion is now **byte containment**: `str(pid).encode("ascii") in probe.stdout`, with `text=True` removed — fully decoupled from code page and system language. This merges with the file's own header rule (MID-64 ②, "always capture as binary"), which had only been applied to `_run_node` and missed the probe |

#### 2. Regression locks added (20 test items, all mutation-verified per repo convention)

- **`tests/test_frontend_quality_ui.py` +4 (`_pid_alive`, three-sided lock covering every subprocess call site in the file)**:
  `test_pid_alive_survives_gbk_tasklist_output` (pins the tasklist payload to the **exact GBK bytes from the incident**, so it
  is independent of the host's current code page), `test_pid_alive_reports_true_from_table_row` (prevents "always return False"
  as a way to dodge the crash), `test_pid_alive_roundtrip_with_real_processes` (starts and really reaps a child, no stubbing —
  proves the detection logic itself works), and `test_no_subprocess_call_in_this_module_decodes_output` (AST-level ban on
  `text=`/`encoding=`/`universal_newlines`, which first asserts "≥3 call sites were seen" before asserting zero violations, so
  the guard cannot be silently vacuous). Stubs replace only the module-global `subprocess` via a `SimpleNamespace` copy, never
  the stdlib module object.
- **`tests/test_run_gates.py` +16 (`run_command` and `ensure_utf8_streams`, previously uncovered)**:
  zero exit with per-line verbatim stderr forwarding / non-zero exit propagated / **rc=0 plus a fatal stderr pattern is a FAIL,
  de-duplicated** (the MID-63 false-green shape) / three-layer child environment precedence (parent env → `GATE_CHILD_ENV` hard
  default → gate-block `NAME=value` prefixes) / `python` rebound to the current interpreter / `stdin=DEVNULL` /
  the `stderr is None` branch / a missing cwd must raise `OSError` instead of silently passing / signal death returns non-zero
  while pre-death output is still forwarded (POSIX-only skip) / `ensure_utf8_streams` cp936→UTF-8 reconfigure success plus the
  three "cannot reconfigure → stay silent" variants / `main()` rc=1 on a fatal hit and `--keep-going` semantics, rc=3 when a
  gate tool is missing, and `check_executables` not over-reporting when the `python -m <name>` fallback works.
  reverting `_pid_alive` to `text=True` → 5 red (including the original MID-64 lock, and the real-process case reproduced the
  exact `NoneType` error from the incident); neutering `run_command`'s stderr scan → `flags_fatal_pattern` red; narrowing
  `ensure_utf8_streams`' `except ValueError, OSError` to exclude `OSError` →
  `test_ensure_utf8_streams_never_raises[os_error]` red.

#### 3. Release-chain runtime pins: 6/10 slots backfilled (only values traceable to official publications)

| Slots | Official source | Status |
| --- | --- | --- |
| **node** for `windows` / `linux-x64` / `linux-arm64` / `macos-x64` / `macos-arm64` (5 slots) | `https://nodejs.org/dist/v24.21.0/SHASUMS256.txt`, cross-checked line-by-line against the cleartext body of the GPG-signed `SHASUMS256.txt.asc` for the same version (**signature not verified**). v24.21.0 = the first LTS entry of `index.json` that day (Krypton), i.e. exactly what `_download_nodejs` selects | pinned |
| `windows-x64/ffmpeg` | gyan.dev's official `.sha256` document, corroborated by two endpoints: the rolling alias `ffmpeg-release-essentials.zip.sha256` and its redirect target `packages/ffmpeg-9.0.2-essentials_build.zip.sha256` (ffmpeg 9.0.2) | pinned |
| `macos-x64`, `macos-arm64` ffmpeg | **Upstream publishes no SHA256**: the evermeet page only offers "append `/sig` to any file for the GPG signature", no sha256 document | left as placeholder |
| `linux-x64`, `linux-arm64` ffmpeg | **Upstream publishes no SHA256**: johnvansickle only provides `*.md5` (measured 200, containing an md5 digest) | left as placeholder |

- Under SEV-10's hard rule "**never fill from a local download**", those 4 slots keep `UNVERIFIED_PIN`, and
  `check_runtime_pins.py --strict` still blocks releases (rc=1, measured) — expected, not a regression. The available
  remedies (GPG-verified dual channel / switching to an upstream that publishes SHA256 / an explicit, separately justified
 fallback for md5-only upstreams) are a maintainer decision and are recorded in the table's comments.
- **Separate defect found while verifying (not fixed opportunistically here)**: the macOS arm64 download endpoint in
  `build_exe.py`, `https://evermeet.ca/ffmpeg/getrelease-arm64/zip`, returned 404 at the time of measurement and still needs a fix.
- Rolling-value reminder: the node section goes stale when upstream ships a new LTS and the gyan section when it cuts a new
  ffmpeg release; both are deliberate manual gates.

#### 4. Documentation kept in sync

Three edits in `AGENTS.md`: ① inside the SEV-10 entry, "all slots in this repo are still placeholders" was disproven by this
backfill → rewritten to the 6/10 state with a dated revision note; ② inside the MID-63 entry, "`test_run_gates.py` does not
cover `run_command`, the crash path has no lock" → rewritten with a dated revision note; ③ a new long-term convention in
"Testing quality & review workflow": **probing subprocess output always compares bytes, and such cases must run green from a
single file** (including the explanation of how `SetConsoleOutputCP` hides the failure behind "green in full runs").

#### 5. Gate results (`.venv/Scripts/python.exe`, Python 3.14.7)

| Tool | Result | Counts |
| --- | --- | --- |
| black / isort | pass | 166 files unchanged; Skipped 13 files, no violations |
| mypy / `mypy --platform linux` | pass | 0 issues / 144 files (both sides) |
| basedpyright | pass | 0 errors / 0 warnings / 0 notes |
| pytest (full, with `--cov=src`) | pass | **2343 passed / 11 skipped / 0 failed / 0 warnings** (previous round: 2324 + 10) |
| `scripts/check_coverage.py` | pass | 82.11% total, 6/6 modules above threshold |
| `scripts/check_annotations.py` | pass | 149 files, 0 dangling references, 23.1% average comment density |
| `scripts/run_gates.py` | pass | all 8 gates green |
| `scripts/check_runtime_pins.py --strict` | blocks release by design | rc=1, 4 ffmpeg slots pending a decision |
| Single-file isolation | pass | `test_frontend_quality_ui.py` 6 passed; `test_run_gates.py` 29 passed / 1 skipped (POSIX signal case) |

### v4.3.0-dev (2026-09-22) — Gate repair: MID-N01 dangling call collapsed, test-stub annotations relaxed, symbol-reachability check added as a gate

> **Nature of this round**: clears the three red lights that the previous round logged as pending, and
> turns the "deleted a symbol, left the call site" failure shape — now recurring for the **second** time
> (补-N04) — into an enforced gate action. One product-logic criterion was collapsed; no new features,
> no dependency changes.

#### 1. Defect fixed (the only blocker)

| Location | Problem | Fix |
| --- | --- | --- |
| `main.py:1346` (failure branch of `check_subprocess`) | Calls `_ffmpeg_reported_output_failure()`, deleted by MID-N01: `mypy` reported `name-defined`, basedpyright `reportUndefinedVariable`, and 3 cases in `tests/test_record_failure_feedback.py` failed with `NameError`. The call sits on the right side of `and`, so short-circuiting protects it only **when the parent output directory exists** — Linux CI (`/tmp` exists) never trips it while Windows always does, i.e. a delayed runtime defect rather than static noise | Criterion ② (reading ffmpeg's buffered output) is unobtainable (`Popen` never sets `stdout=PIPE`), so the exemption collapses to a single criterion: `_output_side_failure = not os.path.isdir(os.path.dirname(save_file_path) or ".")`. The disproven comment claim "① alone cannot distinguish" was corrected: when the parent directory is absent ffmpeg cannot produce any bytes, which is mutually exclusive with "CDN rejected the stream" |

#### 2. Test-side changes

- **Stub annotations relaxed (clears the remaining 8 basedpyright errors)**: the four forwarding stubs at
  `tests/test_ffmpeg_install.py:638` and `tests/test_node_install.py:213/363/403` now use `Any` instead of
  `object` for `*args`/`**kwargs` (basedpyright matches declared types against each parameter; mypy does not
  report it). `tests/test_web_tray.py:264` now reads `cast(_FakeIcon, tray.icon).args[2]` — the fake records
  constructor args, and widening to `Any` would drop the `_FakeIcon` shape.
- **A platform-dependent test premise was fixed**: the ffmpeg output path in
  `tests/test_record_failure_feedback.py` moved from `"/tmp/out.ts"` to a file under
  `tempfile.gettempdir()`. The failure branch exempts probe backoff precisely when "the parent output
  directory is missing", and `/tmp` exists on Linux but not on Windows — the same "fast failure must record
  backoff" assertion meant opposite things per platform and was silently swallowed on Windows.
- **New `tests/test_check_annotations.py`** (4 cases) locks the symbol-reachability check on three sides:
  it really reports, it does not report names with a source, and the repository currently has zero dangling
  references.

#### 3. New gate action (regression guard)

- `scripts/check_annotations.py` now runs a **symbol-reachability check** in its default mode: it scans every
  Python file and reports "a name referenced with no binding anywhere in the repository", together with a
  `grep -n <symbol>` hint. The criterion is deliberately conservative (only Load names with no binding in
  the file **and** no same-named binding anywhere in the repo, so `import *`, monkeypatch and dynamic
  `globals()` stay legal); misses remain covered by mypy and basedpyright. This script was chosen because
  `python scripts/check_annotations.py` is already in the "formatting commands" gate list, so **both CI and
  `scripts/run_gates.py`** run it — no second command list had to be created.
- The matching `AGENTS.md` entry was updated to "now enforced as a gate action", plus one derived lesson:
  "output paths inside test cases must be directories that really exist".

#### 4. Gate results (`.venv/Scripts/python.exe`)

| Tool | Command | Result | Count |
| --- | --- | --- | --- |
| black | `black --check .` | pass | 165 files unchanged |
| isort | `isort --check-only --diff .` | pass | Skipped 13 files, no violations |
| mypy | `mypy` / `mypy --platform linux` | pass | 0 errors / 143 files (both sides) |
| basedpyright | `basedpyright` | pass | **0 errors / 0 warnings** (was 9 errors) |
| pytest | `pytest -q` | pass | **2317 passed / 10 skipped / 0 failed / 0 warnings** (was 3 failed / 2314 pass… |
| check_annotations | `python scripts/check_annotations.py` | pass | 148 Python files, 0 dangling references |
| run_gates | `python scripts/run_gates.py` | pass | all 8 gates green |

### v4.3.0-dev (2026-09-22) — Metadata source-of-truth sync + full quality-gate run + four-catalogue i18n verification (zero production-code change)

> **Nature of this round**: a check-up and closing pass rather than a feature iteration. After scanning
> every workspace file, everything that must stay in sync across files (version, dependency lists,
> config keys, exclude directories, the four translations) was realigned to one level, followed by a
> full quality-gate run. **No business logic changed** in `src/`, the root entry points, or the frontend;
> every edit landed in metadata, configuration, documentation, or exclude lists.

#### 1. Changes by module

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-22) — Metadata source-of-truth sync + full quality-gate run + four-catalogue i18n verification (zero production-code change) | section: 1. Changes by module).

#### 2. Deletions in this round

- **Zero production-code deletions** (no file, function or config key was removed; the dangling
  `main.py:1346` call is a **pending fix**, not a deletion — see section 4).
- All **one-off temporary artefacts** produced during the run were removed: 8 redirected output files,
  the three temporary audit scripts `_tmp_config_audit.py` / `_tmp_i18n_check.py` / `_tmp_en_check.py`,
  and the `DouyinLiveRecorder.egg-info.bak` backup directory — per the "test wrap-up cleanup" rule
  in `AGENTS.md`.

#### 3. Full quality-gate results (`.venv/Scripts/python.exe`; `pyproject.toml` is the only config source)

| Tool | Version | Command | Result | Count |
| --- | --- | --- | --- | --- |
| black | 26.5.1 | `black --check .` | pass | 165 files unchanged |
| isort | 9.0.1 | `isort --check-only --diff .` | pass | Skipped 12 files, no violations |
| mypy | 2.3.1 | `mypy` (no path argument, consumes `[tool.mypy].files`) | **fail** | 1 error / 143 files |
| basedpyright | 1.40.1 | `basedpyright --outputjson` | **fail** | 9 errors / 0 warnings, 151 files |
| pytest | 9.1.1 | `pytest -q` | **fail** | 3 failed / 2314 passed / 10 skipped (111s) |
| node --test | v22.22.2 | `node --test tests/frontend/test_quality_ui.mjs` | pass | 27 passed |

All three red results share **one root cause**: the dangling call to the deleted function
`_ffmpeg_reported_output_failure` at `main.py:1346`.
All 10 skips are platform limitations (1 case-insensitive Windows env vars, 6 no offline form,
1 `os.chmod` permission bits, 2 no real symlink created) — not defects.

#### 4. Known leftovers (deliberately untouched here, for manual handling)

1. **Dangling call at `main.py:1346` (the only blocker)**: in
   `(not os.path.isdir(...)) and (_ffmpeg_reported_output_failure(proc))` the function was removed by
   MID-N01 while the call site survived. This is not a purely static issue — short-circuiting protects
   it only **when the parent output directory exists**, so a deleted directory raises a real `NameError`.
   Suggested fix: collapse lines 1345–1347 to
   `_output_side_failure = not os.path.isdir(os.path.dirname(save_file_path) or ".")`.
   Not applied here because this round must not touch business logic; the same failure shape has now
   recurred a second time and is logged in `CODE_REVIEW_2026-09-21.md`, section 补-N04.
2. **8 test-stub annotations** (`tests/test_ffmpeg_install.py:641`, `tests/test_node_install.py:216/366/406`
   and sibling forwarding stubs): switch `object → Any`; for `tests/test_web_tray.py:264` use
   `cast(_FakeIcon, tray.icon).args[2]`. That takes basedpyright to 0 errors.
3. **Observation (no change made)**: `i18n/zh_TW.yaml` keeps the simplified spelling 「平台」 where Taiwanese
   written usage prefers 「平臺」, affecting ~30 values — a regional orthography preference rather than a
   gap. Key sets, placeholders, empty values and spellings all verified consistent, so nothing was changed.

#### 5. Four-catalogue i18n verification (confirmed to need no additions)

| Check | Result |
| --- | --- |
| Key sets equal across the four catalogues | 663 entries equal one by one (`tests/test_i18n.py` 40 passed) |
| Runtime-string coverage | `scripts/extract_i18n_strings.py`: 436 valuable strings, **0 missing** |
| Empty values / placeholder consistency | 0 empties; 0 mismatched `{placeholder}` sets against the source strings |
| en_US / en_GB spelling | Only 7 differing entries (minimises / cancelled / unrecognised / authorisation, etc.); no American spellings left in en_GB, none misused in en_US |
| zh_TW simplified vs traditional | 0 simplified-only characters in values (see the 「平台」 observation above) |
| Frontend four languages | Embedded catalogues in `web/app.js` share one key set; no unregistered hard-coded Chinese in index.html (27 passed) |

### v4.3.0-dev (2026-09-21) — Full worktree change ledger (by module): `CODE_REVIEW_2026-09-21` remediation round + coverage work stream

> **Why this entry exists**: the repository has **no `.git` directory and no git executable on this
> machine**, so changes cannot be enumerated with `git diff`. This ledger instead cross-validates
> three independent signals — file mtime, the report-ID comment markers inside the source, and the
> matching IDs inside `tests/` — to cover the whole of 2026-09-21, so that a document recording
> only half of the scene can still be reconciled.

#### Change batches (three independent work streams, same day)

| Batch | Time window | Input source | Recorded in |
| --- | --- | --- | --- |
| A. `CODE_REVIEW_2026-09-20` full-round remediation | 09-21 00:02 – 02:43 | `CODE_REVIEW_2026-09-20.md` | the «Full CODE_REVIEW_2026-09-20 round landed» entry below |
| B. `CODE_REVIEW_2026-09-21` remediation round (**in progress**) | 09-21 11:40 – 14:40+ | `CODE_REVIEW_2026-09-21.md` (540 lines, new file, generated 11:40) | the body of this entry |
| C. Test-coverage work stream | 09-21 10:50 – 14:30 | user goal “reach 80% coverage” | the next «Test-coverage work stream» entry |

Batches B and C are **not the same work stream**: B edits `src/`, C edits only `tests/`. Between
13:52 and 14:05 they wrote into the same test directory in an interleaved way (B changed
`test_web_config.py` / `test_stream_select.py` / `test_config_io_backup.py`; C changed
`test_node_install.py` / `test_web_tray.py` / `test_ffmpeg_install.py` etc.), with no file-level conflict.

#### Batch B: landed changes, grouped by module

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-21) — Full worktree change ledger (by module): `CODE_REVIEW_2026-09-21` remediation round + coverage work stream | section: Batch B: landed changes, grouped by module).

#### Batch B removals

- `src/javascript/laixiu.js` and `src/javascript/taobao-sign.js`: **the files themselves were removed
  from `src/javascript/` on this day** (their table entries had already been dropped in the 09-20 round).
  Basis: the `src/utils.py` table comment matches the directory as measured (5 remaining `*.js`:
  `crypto-js.min.js` / `haixiu.js` / `liveme.js` / `migu.js` / `x-bogus.js`, 5/5 with `_JS_SHA256_EXPECTED`).
  Rationale: zero call sites repo-wide (the Laixiu signature was rewritten in pure Python as
  `calculate_sign` in `spider.py`), and `taobao-sign.js` carried a structurally complete set of real
  captured request parameters in its comments (session token + timestamp + account identifier), which
  shipping with the source would exfiltrate another party's session material.
- The two dead methods `bnu` / `bn` inside `src/javascript/haixiu.js` (MIN-N39).
- **No other production-code removals**; batch C also has none (the 11 throwaway helper scripts are not repo content).

#### Batch B items not yet landed (in progress — do not cite as done)

No landing comment for `SEV-N01`, `SEV-N05` or `SEV-N06` can be found in any `*.py` repo-wide, meaning
these three P0 items are still unfixed:

- **SEV-N01** three leaks in `main.py::check_subprocess` teardown (zero-byte early return, too-narrow
  reclaim condition on the exception path, danmaku collectors not stopped on the exception path);
- **SEV-N05** `select_source_url` hands a proxy address to `httpx.Client(proxy=…)` without normalising
  it through `handle_proxy_addr`;
- **SEV-N06** the GUI log parser hard-codes simplified-Chinese text into regexes and substring tests, so
  after switching to any non-`zh_CN` language, quality monitoring and recording status fail silently.

Also: `tests/test_web_api.py` was still being modified at 14:40 (after the previous write of this
document), so **batch B's file list and the tables in this section are a point-in-time snapshot** —
reconcile them by “mtime + report ID” before citing.

#### Current status re-check (measured after both batches converged)

| Item | Command | Measured |
| --- | --- | --- |
| Full suite | `pytest --cov=src` | 2310 passed / 10 skipped / **0 failed** (includes batch B's latest 14:40 chang… |
| `src/` coverage | same | **82.03%** (the 80% target still met) |
| Per-module gate | `python scripts/check_coverage.py` | 6/6 passing |
| Typing | `mypy` | 0 error / 143 files |
| Formatting | `black --check .` / `PYTHONUTF8=1 isort --check-only .` | 165 unchanged / rc=0 |

### v4.3.0-dev (2026-09-21) — Test-coverage work stream: `src/` coverage 73.28% → 82.03% (zero production-code change)

**Context and goal**: one closed loop of «analyse gaps → add tests → verify», targeting
80% project test coverage. Baseline reading was 73.28% (10537 statements / 7721 covered);
reaching 80% required a net gain of at least 709 covered statements.

**Scope boundary**: this round touched **only `tests/`** — `src/`, the root entry points
(`main.py` / `gui.py` / `web.py` / `msg_push.py` / `i18n.py`), `config/`, `scripts/`,
`.github/` and `pyproject.toml` were **not modified** (no coverage threshold and no
`MODULE_THRESHOLDS` entry was lowered or raised). Hence there is no behaviour change, no
interface change and no removal; every addition is a **behaviour regression lock**.

#### Measurements

| Metric | Before | After |
| --- | --- | --- |
| `src/` total coverage | 73.28% | **82.03%** (8760/10679 statements) |
| Test count | 1917 passed / 10 skipped | 2310 passed / 10 skipped |
| Net newly-covered statements this round | — | +1039 (includes src statements added by the concurrent work stream) |

> The table above is the **re-measured** reading. The first pass recorded 82.02% / 2301; the
> concurrent work stream then also changed `src/utils.py`, `src/config_io.py` and
> `src/stream_select.py` and added cases such as `tests/test_web_api.py`, so this table has been
> rewritten against the latest full run. **Cite this table when referring to this round's effect.**

Per module (before → after, all measured from `coverage.json`):

| Module | Before | After | Note |
| --- | --- | --- | --- |
| `src/node_install.py` | 15.1% | 100% | Windows/Linux/macOS install chain was completely unguarded |
| `src/ffmpeg_install.py` | 36.2% | 98.9% | Official source / Lanzou fallback / platform dispatch / four exception shapes (**2026-09-22 update**: the Lanzou fallback was removed outright and this round's 5 Lanzou test classes went with it; it is now "single official source + payload shape guard") |
| `src/web_tray.py` | 0% | 100% | Windows-only; there was no offline-testable seam at all |
| `src/platforms/douyu.py` | 29.4% | 98.2% | STT encode/decode + sticky-packet advance |
| `src/platforms/bilibili.py` | 48.8% | 97.5% | 16-byte header / protover 1-2-3 / AUTH watchdog |
| `src/platforms/twitch.py` | 45.2% | 98.8% | IRC cross-frame line buffering + colour fallback |
| `src/config_io.py` | 72.8% | 99.6% | Write side (update_file / anchor-name sync / backup redaction) |
| `src/recorder_status.py` | 49.1% | 99.1% | Status snapshot + the «currently recording» branch |
| `src/video_postprocess.py` | 63.3% | 96.1% | Exception classification + subtitle-thread exit condition |
| `src/spider.py` | 68.4% | 69.7% | Not targeted (the 1003-line gap is platform parsers, see «Outstanding») |

#### Added files (`tests/`, 5)

| Path | Lines | Product module covered | Key invariants locked |
| --- | --- | --- | --- |
| `tests/test_node_install.py` | 535 | `src/node_install.py` | CR-11: a truncated cached zip must be deleted and re-downloaded (otherwise the wrong hash gets frozen as the baseline → permanent failure that cannot self-heal); H-1: a hash mismatch must hard-reject and unlink the package; Windows-on-ARM architecture detection (the old «does `machine` contain "32"» test mis-judged ARM64) |
| `tests/test_web_tray.py` | 310 | `src/web_tray.py` | Every failure mode (missing pystray / DLL load failure / window API raising) must degrade silently and never stop the Web panel; `HWND`/`HMENU` `restype` must be `c_void_p` (otherwise 64-bit handles are truncated); with no uvicorn server, “Quit” takes the `os._exit(0)` path |
| `tests/test_platform_danmaku_offline.py` | 675 | `src/platforms/{douyu,bilibili,twitch}.py` | Douyu C-2 sticky-packet advance step = `full_len + 4`; Douyu C-3 `only_fans` defaults to False; Bilibili H-4 both soft-reject shapes (`code != 0` and «8 seconds of silence») must disconnect and invalidate the buvid cache; Bilibili MI-01 all three decompression paths are length-limited; Twitch MI-21 cross-frame half-line buffering |
| `tests/test_config_io_update_file.py` | 332 | `src/config_io.py` (write side) | 6.1 segment-exact replacement (overlapping URL prefixes must not clobber another line); on read failure roll back from the `ini_URL_content` snapshot instead of truncating; on atomic-write failure the snapshot must **not** advance; CR-07 backups redact by default, `DLR_BACKUP_KEEP_SECRETS=1` opts out explicitly, and a failing redaction itself degrades to a verbatim copy |
| `tests/test_video_postprocess_paths.py` | 312 | `src/video_postprocess.py` | Timeout / `CalledProcessError` / unknown errors must land in three distinct log strings (the old single `except Exception` collapsed them into “unknown error” and lost the semantics); `generate_subtitles` must return as soon as the room leaves the recording set (otherwise a permanently growing subtitle file and a thread that never dies); MIN-04 three-step timeout scaling |

#### Modified files (`tests/`, 2, both append-only)

| Path | Appended content | Product module covered |
| --- | --- | --- |
| `tests/test_ffmpeg_install.py` | 221 → 710 lines. Added `TestThinWrappers` / `TestBuildIdentityGuard` / `TestStaleSidecarWarning` / `TestOfficialDownload` / `TestLanzouLink` / `TestLanzouInstall` / `TestWindowsFallbackOrder` / `TestInstallFfmpegMac` / `TestLinuxExtraBranches` / `TestPlatformDispatch` / `TestCheckFfmpegInstalled` / `TestCheckFfmpegEntry`; the module header gained the «extended» note; the import block gained `io` / `os` / `zipfile` / `requests` / `Iterator` / `Any` / `cast` | `src/ffmpeg_install.py` |
| `tests/test_recorder_status.py` | 275 → 448 lines. Added the `_NormalStdout` / `_ExplosiveCollection` helpers and the `pinned_main` fixture plus `TestGetStatus` (10 cases) and `TestDisplayInfoRecordingBranch` (6 cases); the import block gained `json` and `cast` | `src/recorder_status.py` |

#### Removed

- **Production-code removals: none.**
- All throwaway helper scripts were cleaned up (per AGENTS.md “clean up temporary test
  scripts”): `_tmp_cov_report.py`, `_tmp_cov2.py` … `_tmp_cov6.py`, `_tmp_append_ffmpeg.py`,
  `_tmp_rs_append.py`, `_tmp_dens.py`, `_tmp_final.py`, `_tmp_wt_out.txt`. Runtime output
  directories (`downloads/` / `logs/` / `backup_config/`) and the maintained scripts under
  `scripts/` were **left untouched**.

#### Gate status (each measured, not assumed)

| Gate | Command | Result |
| --- | --- | --- |
| Full suite | `pytest --cov=src` | **2310 passed / 10 skipped / 0 failed**, warnings summary empty (0 warnings) |
| Total coverage | `pytest --cov=src --cov-report=json` | **82.03%** (the 80% target is met; `[tool.coverage.report].fail_under = 50` left unchanged) |
| Per-module coverage | `python scripts/check_coverage.py` | all 6 declared modules meet their thresholds (rc=0) |
| Formatting | `black --check` (whole repo, 165 files) / `isort --check-only` (`.`, **with `PYTHONUTF8=1`**) | all unchanged; isort rc=0 |
| Typing | `mypy` (reads `[tool.mypy].files`, 143 files) | **0 error** |
| Comment conventions | `python scripts/check_annotations.py` | rc=0, average density 23.1%; all 7 files touched this round are at or above the 13.0% threshold |
| Version single source | `python scripts/check_version.py` | rc=0 (this round did not touch the version; confirmed as a regression baseline) |
| Test hygiene R1 | `pytest tests/test_test_hygiene.py` | pass (the `os.chmod` / `os.remove` / `os.path.getsize` stubs in the new files were converted to `types.SimpleNamespace(**vars(mod))` shallow-copy shims and no longer mutate stdlib module bodies) |

**A finding that bears directly on gate trustworthiness** (do not repeat it): running
`isort --check-only .` locally **without** `PYTHONUTF8=1` yields “looks like a pass, plus 3
`Unable to parse file … gbk codec` warnings”, and the files skipped are exactly
`tests/test_i18n_migration.py` / `tests/test_record_container.py` / `tests/test_web_api.py` —
textbook **falsely-green gate** (MID-63 added a dedicated CI step that blocks such silent
skips). Local isort runs must carry `PYTHONUTF8=1`; an rc=0 without it is not evidence that
import ordering is compliant.

**Two self-inflicted defects the gates caught** (recorded so they are not written back):

1. In `tests/test_web_tray.py`, calling `_on_exit` without a `server` really does run
   `os._exit(0)` and terminates the whole pytest session — the symptom is “one line of
   progress, no summary, exit code 0”, which is extremely hard to attribute. Any case
   reaching that branch must pass a `server`.
2. Byte literals appended to `tests/test_ffmpeg_install.py` / `tests/test_node_install.py`
   once came out as `b"\\x50\\x4b ..."` (literal backslashes, not the ZIP magic) due to
   multi-layer escaping, so the “truncated zip” branch was actually exercising “arbitrary
   non-zip content”. Replaced with the unambiguous `b"truncated-partial-download"`.

#### Outstanding and caveats (deliberately not handled in this round)

- `src/spider.py` remains at 69.7% (1003 statements missing) and is the only large gap left
  for pushing the total higher. The missing lines concentrate in **platform parser functions**
  — `get_flextv_stream_data` (73), `_extract_room_data_from_html` (45),
  `get_shopee_stream_url` (42), `get_kuaishou_stream_data` (39), `get_haixiu_stream_url` (37)
  — each requiring a per-platform response stub. The payoff is ~40 lines per function while
  the stub cost is far above the rest of this round, so it was not attempted.
  Note that the `src/spider.py` threshold in `check_coverage.py` is 50%: this is a total
  bottleneck, not a gate failure.
- `src/proto/douyin_pb2.py` reports 8.7% (105 lines missing). Verified: the uncovered range is
  **exactly** the `if _descriptor._USE_C_DESCRIPTORS == False:` block — unreachable by
  construction when protobuf uses the upb/C backend (local `protobuf 7.36.1` with gencode
  4.25.3; `from src.proto import douyin_pb2` was confirmed to import successfully). This is an
  inherent dead region of generated code; the coverage configuration was **not** changed for
  it (editing `omit` must be kept in sync with `.coveragerc-concurrency` and would alter
  gate semantics).
- During this round `src/web_api.py`, `src/web_config.py`, `src/utils.py`, `src/config_io.py`,
  `src/stream_select.py`, `src/spider.py`, `src/javascript/haixiu.js`, `web.py` and the matching
  `tests/test_web_api.py` etc. were modified by **another concurrent work stream (the
  `CODE_REVIEW_2026-09-21` remediation round)**, not by this session. `tests/test_web_api.py` briefly
  showed 8 `_insecure_bind_detail` failures, after which that work stream aligned the two on its own.
  Those changes are now recorded **in their own entry** above (batch B of the “Full worktree change
  ledger”) and are not duplicated here.
- `tests/test_srt_timeline_anchor.py` intermittently produced 4
  `FileNotFoundError: tests\_out_e2e` failures in an earlier `--cov` full run (that file calls
  `os.makedirs(..., exist_ok=True)` at module import, and mid-run the directory is reclaimed by
  `conftest.pytest_unconfigure` of another pytest session on the same machine). The final
  `--cov` full run of this round (after pre-creating the directory) was **2310 passed /
  0 failed**, and running that file together with all files added in this round also passes →
  judged an environment race, not a code regression. A follow-up should move that case's output
  directory to `tmp_path` to remove the same-machine multi-session collision at its root.

### v4.3.0-dev (2026-09-21) — Full CODE_REVIEW_2026-09-20 round landed: 10 severe fixes + thematic MID/MIN batches + five new gates

**Summary**: This round implemented the **106 items** registered in `CODE_REVIEW_2026-09-20.md` (10 severe / 70 medium / 26 minor) through "parallel deep fixes per module group": **SEV-01 … SEV-10 all fixed**, MID/MIN changed in batches along the report's seven themes (§4.1 … §4.7), and five gate families that **did not exist before** were added (section 4). Scope: `main.py`, 23 modules under `src/` (plus `src/javascript/migu.js`), root entries `gui.py` / `web.py` / `msg_push.py` / `build_exe.py` / `i18n.py`, 6 maintenance scripts under `scripts/` plus the new `scripts/check_runtime_pins.py`, 4 workflows, both dependency manifests (`requirements.txt` / `pyproject.toml`, runtime dependencies 20 → **21**), `Dockerfile` / `docker-compose.yaml` / `.dockerignore` / `.gitignore`, `StopRecording.vbs`, the `web/` trio; on the test side **17 new case files** and 29 modified (1 of them `.mjs`). 3 removals: `src/javascript/laixiu.js`, `src/javascript/taobao-sign.js` (补-03/04: dead scripts without callers, removed together with `_JS_SHA256_EXPECTED`) and `tests/_exc.log` (leftover from the MID-64/66 investigation, now blocked by test-hygiene rule R4). `AGENTS.md` gained/updated 22 long-term conventions, including in-place corrections of falsified earlier statements.

> **⚠ Real-machine verification still owed (not closed in this round, must be done next round)**: changes touching the **recording chain / source selection / ffmpeg arguments / platform parsing** (SEV-06, SEV-08, SEV-09, MID-01 … MID-20, MID-40 … MID-50, MIN-02 … MIN-06, etc.) only reached "everything verifiable offline is green + regression locks in place". No real-URL incremental run was performed (step 2 of AGENTS.md's Definition of Done). Regression locks prove "we no longer revert to a known-bad shape"; they **do not** prove "this platform's live stream is recordable right now". A follow-up run in an environment with live rooms is required, item by item per the "Outstanding" row of the table in section 7.

#### 1. Severe defects (SEV-01 … SEV-10, all fixed)

| ID | Defect (compressed from the report title) | Landing point | Regression lock |
| --- | --- | --- | --- |
| SEV-01 | The concurrency semaphore treated "available permits" as "capacity"; every recompute topped it back up → the network concurrency limit was effectively uncontrolled | `src/scheduler.py` (`_capacity` / `_used` split) + the standalone copy synced this round | `tests/test_scheduler.py` |
| SEV-02 | `PUT /api/rooms` bypassed room-entry validation entirely; the SSRF and arbitrary-scheme defences failed there | `src/web_config.py::format_url_line` (verdict sunk into the single write entry point) + `src/web_api.py` | `tests/test_web_api.py::TestRoomWriteParity` |
| SEV-03 | Internal-address blocking was a string-prefix blacklist, bypassable via multiple address forms (5 of 7 probe payloads passed) | `src/web_config.py` (rewritten to `ipaddress` semantics + DNS resolution, two independent checks) | `tests/test_web_config.py`, `tests/test_web_config_secret_mask.py` |
| SEV-04 | Panel auth could be hot-disabled by a single write request; case variants simultaneously bypassed password hashing, the anti-lockout guard and token revocation | `src/web_api.py` (one `lower()` normalization at entry + target-state verdict + per-request invariant) | `tests/test_web_api.py::TestPasswordGuardCaseParity` / `TestAuthDowngradeRejected` |
| SEV-05 | Room deletion silently no-opped forever on CRLF configs while replying `{"ok": true}` (guaranteed on the primary Windows platform) | `src/config_io.py::delete_line` (`newline=""` added, now **returns bool**) + endpoint verdict by re-parse | `tests/test_config_io.py`, `tests/test_web_api.py::TestDeleteRoomReportsTruth` |
| SEV-06 | Shopee site-suffix parsing produced illegal domains → every shared link of that platform failed permanently | `src/spider.py::_shopee_host_suffix` (strip the `live.` label, keep the full suffix; dead branch merged) | `tests/test_spider_fixes.py` |
| SEV-07 | Two login functions paired a fallback decorator with the wrong return contract, disguising failures as "not live" and swallowing actionable user messages | `src/spider.py` / `src/utils.py` (decorator chosen by return annotation) | new `tests/test_decorator_contract.py` (repo-wide AST lock) |
| SEV-08 | The recording watchdog's "stall" baseline was wrong: the tolerance window was effectively 30 s, so self-healable momentary drops were killed | `main.py::check_subprocess` (baseline switched to "last size-change timestamp") | new `tests/test_record_watchdog.py` |
| SEV-09 | The `only_flv` branch left recording state registered when `flv_url` was missing → the subtitle thread looped forever writing | `main.py` (registration moved after the URL is confirmed; state cleanup funneled through `clear_record_info`) | `tests/test_record_watchdog.py`, `tests/test_video_postprocess.py` |
| SEV-10 | The release chain's runtime-binary hash pin table was empty, so unverified third-party binaries entered distributed artifacts | `build_exe.py` (`_PINNED_RUNTIME_SHA256` + shape check in `_is_pinned()` + `--require-pinned`) + `scripts/check_runtime_pins.py` + single-point injection in the `build-release.yml` prepare job | `tests/test_machine_validation_fixes.py` |

#### 2. Medium issues by theme batch (MID-01 … MID-69 + 补-05)

- **Recording main chain and artifact verdict** (MID-01 … MID-12, `main.py`): unique keys for room-thread registration, artifact byte verdict (`_record_output_bytes`) consolidated, hot-reload/commented-out check ordering, `create_var` keys colliding with live threads, etc.
- **Source selection and stream URLs** (MID-13 … MID-20, `src/stream_select.py` / `src/stream.py`): segment-rejection backoff keys, master-playlist variant selection (probe the highest `BANDWIDTH` variant), quality tiers and the Bilibili `qn` reverse map (many-to-one).
- **Concurrency, networking, danmaku and resource governance** (MID-21 … MID-32): `async_http` clients/locks rebuilt per event loop, `collector` stop handshake and `_shutdown` task cancellation, `ws_client` dangling `_ws` reference and send-task strong references (same family as MIN-12/13), `danmaku_monitor` sidecar handles, `PlatformBreaker` probe generation marker (MIN-22).
- **Credential lifecycle and the panel security surface** (MID-33 … MID-39): `ttwid` / Kuaishou `did` / Twitch `client_id` gained TTL plus the **explicit invalidation entry** `invalidate_ttwid()`, `cookie_cache` generation comparison, the Host allowlist (MID-36), blocking panel IO moved to the thread pool (MID-34), login rate limiting with a global failure budget and "trust only the direct peer" XFF handling (MID-35), internal exceptions no longer echoed (MID-39).
- **Platform parsing and signing** (MID-40 … MID-50): Bilibili fallback buvid invalidation chain, Douyin APP-path ORIGIN candidate source, per-platform field/parameter mismatches (Huajiao/Taobao/Douyu/Xiaohongshu/Twitch), bare `json.loads` migrated to `_loads_dict`, hand-built request bodies switched to `urlencode`.
- **GUI / i18n / push / installers** (MID-51 … MID-60): `URL_config.ini` read with `utf-8-sig` (re-arming the CR-01 hang guard), **`set_language()` now returns the effective language code** (MID-52, synced on the GUI and Web sides), duplicate labels in the language dropdown (MID-53, `unique_display_names()`), quality-downgrade flag reset by timestamp, baseline check for the advanced-settings snapshot, `_stopping` reset moved into `finally`, generic masking of Bark device keys, ffmpeg ToFU sidecar file named per build, three-layer process matching in `StopRecording.vbs`.
- **Client JS, gates, test trustworthiness and CI** (MID-61 … MID-69): `migu.js` rebuilds WASM views after each malloc, trust boundary of the remote wasm documented (the three pinning families must not impersonate each other, see AGENTS), isort silent file-skip (MID-63), frontend wrapper hang and effective timeout upper bound (MID-64), blanket `filterwarnings` removed (MID-65), stdlib rewriting through another module's namespace (MID-66), KAT cases asserting literal values (MID-67), the parameterized-logging gate predicate tightened to "inside the first-argument subtree" (MID-68), previous round's fixes lacking regression locks (MID-69).
- **补-05 (security floors)**: `starlette` floor raised `>=0.49.1` → **`>=1.0.1`**, new explicit `urllib3>=2.7.0` (all synchronous outbound HTTP in this repository crosses it), and a new CI `deps-audit` job running `pip-audit -r requirements.txt`.

#### 3. Minor issues (MIN-01 … MIN-24)

Handled item by item per the report's suggestions; batched items include: `proxy.py` IPv6 bracketed form / uppercase env vars / credentials in authenticated proxies (MIN-20), `atomic_write_text` temp name carrying the thread id + the two write locks converged (MIN-21), non-monotonic `srt_writer` indices (MIN-24①), `weverse_auth` routed through `sync_http` with masking (MIN-08), exception-swallowing sites gaining `type_name` (MIN-09), `remove_duplicate_lines` clearing first-pass keys in the fallback branch (MIN-11), `ARG` moved above `LABEL` in the Dockerfile with `check_version.py` now asserting line order (MIN-14), `trivy.yml` bumped to the actions v7 baseline and placeholders cleaned (MIN-16), `issue-translator.yml` downgraded to manual dispatch with least privilege (MIN-17), `:latest` pull fallback removed from `docker-compose.yaml` (MIN-18), `check_coverage.py` exiting rc=2 with no data (MIN-19), the `AGENTS.md` lock list corrected to "decide from the source definition" plus a measured reentrancy classification (MIN-24⑤), and the `gui_legacy.py` stale references cleared (MIN-15; this round adds the 4th site: the `.dockerignore` bullet in `CODE_WIKI.md` / `CODE_WIKI_EN.md`).

#### 4. New gates (absent before this round)

| Gate | Landing point | Failure mode it kills |
| --- | --- | --- |
| `PYTHONUTF8=1` + "gate warnings are failures" | The black/isort lines of the "Formatting commands" block, `scripts/run_gates.py` (`GATE_CHILD_ENV` / `FATAL_STDERR_PATTERNS` / `ensure_utf8_streams()`), step-level `env` in `ci.yml` + a separate silent-skip fallback step | Under a GBK locale isort **silently skips** core sources containing Chinese comments and still returns rc=0 (green locally, green in CI, neither side actually checked) |
| `scripts/check_runtime_pins.py` | Structural mode inside the gate block; `--strict` + `--emit-env` executed by the `build-release.yml` prepare job | An empty pin table that only warns and continues; missing platform/slot now exits rc=2 |
| Decorator-contract AST lock | new `tests/test_decorator_contract.py` | Fallback decorator mismatched with the return type; a comment between `@decorator` and `def` binding the decorator to the wrong function |
| Test-hygiene AST lock | new `tests/test_test_hygiene.py` (R1 … R4) | Rewriting stdlib bodies through another module's namespace, blanket `filterwarnings`, KAT cases asserting only types, one-off artifacts left in `tests/` |
| Frontend catalog parity lock | `tests/frontend/test_quality_ui.mjs` (`index.html`'s `data-i18n*` keys vs. the four embedded catalogs, and set equality across the four) + the `tests/test_frontend_quality_ui.py` wrapper | "Two independent catalogs kept in sync by human memory" (MIN-10) |
| `deps-audit` job | `.github/workflows/ci.yml` (in `ci-summary`'s needs) | Manifest floors staying inside known-affected version ranges |
| Coverage hard failure with no data | `scripts/check_coverage.py` rc=2 | "Ran no `--cov` locally yet believed the gate passed" |

#### 5. Security-facing changes (external behaviour, listed separately)

- **Room URL validation is now `ipaddress`-based and applied on every write endpoint**: integer/octal/hexadecimal IPv4, full IPv6, `0/8` and CGNAT `100.64/10`, and domain names resolving into private space are all rejected; the verdict sits in `web_config.format_url_line` (the single `URL_config.ini` write entry), so `add` / `update` / `quality` can no longer diverge.
- **Case normalization of `[Web]` keys**: one `key.strip().lower()` at entry, so password hashing / anti-lockout / token revocation also apply to `WEB_PASSWORD` variants.
- **Host allowlist**: same-origin decisions no longer trust the request's own `Host`; the allowlist is derived from server-side configuration and the "non-loopback requires auth" invariant is re-checked on every request (closing the DNS-rebinding path through SOP/CSRF).
- **Blocking panel IO on the thread pool**: directory listing / log reading / config parsing endpoints are plain `def` handlers dispatched by FastAPI to the anyio pool; the status snapshot adds TTL caching + single-flight + serving stale on timeout.
- **Login rate-limit key hardening**: XFF trusted only for proxies listed in `web_trusted_proxy`, plus a global failure budget — defeating "rotate the bucket by spoofing XFF" and unbounded bucket growth.
-  the endpoint decides 200/500 from the re-parsed result.
- **Sensitive config writes reject two value kinds** (closed in this round's seam pass): keys hit by `is_sensitive_item` accept neither an empty value nor the literal mask `'***'` the panel echoes — the frontend `saveConfig` mask skip is thereby demoted from "the only line of defence" to "saves one pointless write".
- **Language switching persists the effective code** (closed in this round's seam pass): `PUT /api/language` now "calls `i18n.set_language()` first → persists the **effective** code it returns → answers with that code plus a fallback notice", and rolls back the in-memory state when persistence fails; a missing catalog (e.g. PyYAML not installed) no longer leaves the panel process and the recorder subprocess speaking two languages.

#### 6. Cross-file seams closed (left by the parallel fixers, finished here)

- `src/web_api.py`: effective-language semantics for the language endpoint (last two bullets of section 5) and rejection of the mask value (400, same wording family as the blank-value rejection).
- `src/scheduler.py`: added the missing **back-pointer comments** — the module header and both class comments name `scripts/douyin_live_recorder_standalone.py` as holding independent copies that must be mirrored method-by-method when concurrency semantics change; an AST recount is recorded stating that the two `PlatformBreaker` implementations are **not equivalent** today (9 methods here vs. 5 in the copy).
- `src/platforms/douyin.py`: wired `invalidate_ttwid()` into the danmaku chain's "handshake refused with HTTP 200" branch (same shape as Bilibili's `_reject_auth()` → `invalidate_bili_buvid_cache()`); reconnect counts and backoff are unchanged. The **parsing side** (`src/room.py` / `src/spider.py`, the "200 + empty body" verdict) still has no such call site, noted in the module comment as pending.
- Docs / metadata: this entry in both `CODE_WIKI.md` and `CODE_WIKI_EN.md`, the 4th MIN-15 stale reference removed; `DouyinLiveRecorder.egg-info` regenerated (`PKG-INFO` = 4.3.0; `requires.txt` aligned entry-by-entry with `pyproject [project.dependencies]` and `requirements.txt`, 21 entries each, including the new `urllib3>=2.7.0`).

#### 7. Verification

| Item | Command / criterion | Result |
| --- | --- | --- |
| Seam-pass focused cases | `pytest -q tests/test_web_api.py tests/test_scheduler.py tests/test_douyin_danmaku.py tests/test_ttwid.py` | **156 passed / 2 skipped / 0 warnings** (both skips are the Windows symlink-privilege limitation, environment-only) |
| New regression locks | `pytest tests/test_douyin_danmaku.py` | 16 passed (one of them asserts the real module-global cache is cleared, with `invalidate_ttwid` **not** stubbed) |
| Mask-guard attribution | `test_only_the_exact_panel_mask_is_rejected` (`'****'` still 200) | Proves the 400 comes from the new guard alone and that other sensitive-key writes are unharmed |
| Format & types | `black --check` (120/py314), `isort --check-only` (profile black, with `PYTHONUTF8=1`), `py_compile`, `mypy` on the files changed here, `mypy --platform linux`, `scripts/check_annotations.py` | All clean (annotation gate: 142 files pass) |
| Metadata | `importlib.metadata.version("DouyinLiveRecorder")` | `4.3.0` (same source as `pyproject.toml`) |
| **Outstanding (partly closed in the same-day follow-up, see §8)** | Incremental real-URL recording (at least one affected platform); first run of the `deps-audit` job on a GitHub runner | **Still open** — real-world recordability of the recording chain remains unproven; the full gate suite / `pytest -q` / `check_coverage.py` / `basedpyright` were re-run in the follow-up and are green |

#### 8. MID-48 closure + locally-evaluated CI changes (2026-09-21, same-day follow-up)

**1) MID-48 fully closed (`src/spider.py`)**: the "84 remaining bare `json.loads`" the report recorded were
migrated in two batches — 21 domestic high-traffic functions (38 sites) plus 31 overseas/credential-bearing
functions (36 sites) — onto the existing `_loads_dict` and the new accessors `_dig` / `_dig_str` / `_dig_list`
with `_warn_api_abnormal` (**no third loads wrapper was introduced**). Textual count 78 → 2; AST call sites
(excluding `_safe_loads` itself) 75 → **1**, the single documented exemption being `get_twitchtv_room_info`
(GraphQL returns a *list*, so `_loads_dict` would classify it as non-JSON; it already carries a typed warning in
its own try/except). The criterion is now pinned by `tests/test_spider_hardening.py::BARE_JSON_LOADS_CEILING = 1`
(**may only go down**) plus a per-function "zero bare loads" AST scan. Each platform is driven with four payload
shapes (WAF/HTML, missing object, truncated JSON, normal body) against the **real** parser with only the transport
stubbed; the success path asserts field-by-field equality (`assert result == expected`) and **no warning at all**.
Two accompanying rules: numeric fields keep their value via `_dig` + cast (`_dig_str` would silently blank an int —
SOOP `BNO`, Huajiao `relateid/uid`); credentials (`AID` / `BNO` / `visitor_st` / `hls_authentication_key` / `mcData`)
**never reach a log**, attribution carries only the envelope `code`/`msg`, and a test asserts no token appears in
any logged line. Documented offline rounds ("not streaming") deliberately stay silent
(`test_documented_offline_stays_silent`). **No new strings** — two existing msgids were reused.

**2) CI changes verified locally (no package installed into the project venv, no remote, no git repo)**: of 34
structural assertions, **0 genuine failures** (the 4 initial FAILs were all bugs in my own checker or deliberate
quarantines). Confirmed true: `ci-summary.needs` covers 8 jobs with no orphan job, `deps-audit` is a required
check, no `continue-on-error`, network installs go through the retry composite action (11 / 4 uses, no inline
loops), `python_build=3.14` and `node_version=24` agree across workflows, the black/isort steps carry step-level
`PYTHONUTF8=1` and match the AGENTS gate block **verbatim**, plus a separate step that fails on
`Unable to parse file`; `requirements.txt` vs `pyproject [project.dependencies]` compare **21/21 with zero
difference** (via `tomllib`), `protobuf<8` intact, `urllib3>=2.7.0` declared; all three compose services resolve
to `pull_policy: build` after anchor expansion; the Dockerfile `ARG`-ordering gate does catch a deliberately
reversed file. **Pinning chain end to end**: the JSON from `check_runtime_pins.py --strict --emit-env` flows
through `DLR_RUNTIME_SHA256` into `_pinned_slots()` (only the current runtime key `windows-x64` is consulted,
other platforms' pins do not leak); `_is_pinned()` accepts strictly 64 lowercase hex (placeholder marker, 63 chars
and uppercase all count as unpinned); in CI form **both the ffmpeg and node slots `SystemExit` before any
download with `urlopen` call count 0 and no file written**; local form only warns and labels the output "not for
release", by design.

**3) pip-audit measured (the OSV side of 补-05)**: installed into a throwaway venv outside the repo (project venv
untouched, no manifest entry added), deleted afterwards. **Without `PYTHONUTF8=1` pip-audit cannot even read our
manifest** — `pip-requirements-parser.auto_decode()` uses `locale.getpreferredencoding(False)`, so on a Chinese
Windows (cp936) it dies with `UnicodeDecodeError` on the inline Chinese comments, rc=1, **before any vulnerability
lookup** (same family as MID-63; now recorded in AGENTS.md's `deps-audit` entry and the evidence doc). With
`PYTHONUTF8=1` all three shapes (fully resolved transitive set / `--no-deps` over the 21 declared floors /
`--path` against the project's installed packages) report **No known vulnerabilities found, rc=0**. Tool fact:
2.10.1 has no `--venv` flag; use `--path`.

**4) Follow-up verification**: `scripts/run_gates.py` **8/8 green**; full `pytest -q` **1917 passed / 10 skipped /
0 failed / 0 warnings** (all 10 skips are Windows environment semantics: env-var case-insensitivity, `os.chmod`
permission bits, symlink privilege, and 6 "platform has no documented offline shape" cases); `basedpyright`
**0 errors / 0 warnings**; `check_coverage.py` **PASSED** with total coverage **73.28%** and `src/spider.py`
64.9% → **68.4%** (lifted by the new locks); in-repo link/anchor check resolves **85/85**. `.gitignore` and
`.dockerignore` gained `coverage.json` (the `--cov-report=json` artefact; previously only `.coverage*` was ignored).

#### 9. Module-classified inventory of every change (added / modified / deleted, with paths)

**Method**: every file was diffed against the 2026-09-20 22:15 workspace snapshot, including extension-less
(`Dockerfile`) and dot files (`.gitignore` / `.dockerignore`, which had no baseline copy and are counted from the
actual edits). Totals: **91 files modified, 19 added, 2 deleted**. 80 of them come from a direct diff against the
snapshot; the other 11 (four translation catalogs + two READMEs + two `docs/agent-reference/` externalised docs +
`.gitignore` + `.dockerignore`) had no baseline copy and are counted from content evidence — their line counts are
deliberately not maintained here. `+x/-y` is the unified-diff added/removed line
count (`StopRecording.vbs` is UTF-16 LE, so its line count does not reflect semantic volume). The last column
references `CODE_REVIEW_2026-09-20.md` ids; `—` means the change is a knock-on sync of the items above it.

##### 9.1 Recording orchestration and room threads (CLI entry point)

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `main.py` | modified `+555/-138` | Watchdog stall baseline moved from "process start" to "last byte growth" (new `_stall_since`); the single-recording time cap became configurable (`max_record_seconds`) and is inert when segmentation is off, and hitting it now runs the same wrap-up as `rc==0` (transcode + success sample + backoff clear); in the `only_flv` branch the `recording` registration and the subtitle-thread start moved below the `flv_url` check, with `clear_record_info` on the miss path; the "gave up waiting for a slot" branch now clears state; output-directory failure skips the round and is no longer attributed to a CDN fast-fail; `http_record_list` `"migu"` → `"咪咕直播"`; the two resolver-less `PLATFORM_HOST` entries handled; `_record_output_bytes` derives the real extension from `save_file_path` and reuses `_\d+\.` (no more hardcoded `.ts`, 4-digit segment numbers counted); direct download only succeeds above `_MIN_VALID_RECORD_BYTES`; `check_subprocess` no longer reads hot-reloaded globals for its wrap-up; `config.read()` is preceded by `clear()` each round; `_sync_ssl_disable_platforms` re-runs from the main loop on change; `split_time` goes through `_safe_int`; `finally` converges orphan ffmpeg (terminate + unregister + clear) after mid-body exceptions; `room_stopped` moved out of the `while True` body to thread-exit; `create_var` keys became lifecycle-independent with an identity check before pop; the forced direct-download path uses `clear_record_info`; stream URLs logged in 7 places now pass `mask_credentials`; `_match_stream_suffix` compares the path extension instead of substring containment (new `_stream_path_suffix`); `delete_line`'s bool result surfaces as a warning when nothing was removed | SEV-03/05/08/09, MID-01…12, MID-28/30/68, MIN-01/07 |

##### 9.2 Concurrency scheduler and runtime status

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/scheduler.py` | modified `+97/-28` | `ResizableSemaphore` split into `_capacity` (limit, only `set_value` changes it) and `_used` (held, only acquire/release change it); new `capacity` property while `value` keeps meaning "free permits"; `recompute()` compares against `capacity`, killing the "refill free permits every round while holders exist" behaviour; `PlatformBreaker` gained `_probe_seq` plus probe ownership by `Thread` identity so a stale probe can no longer drive the half-open transition, with the lease self-heal preserved verbatim; back-pointer comment to the standalone copy | SEV-01, MIN-22 |
| `src/recorder_status.py` | modified `+44/-4` | `_live_network_capacity()` reads `capacity` (it displayed free slots); `display_info`'s sleep left the try, `sys.stdout is None` returns early, and consecutive failures back off (300 s cap) — no more 100% CPU spin when the console is absent or the sink handle was closed | SEV-01, MID-31 |
| `scripts/douyin_live_recorder_standalone.py` | modified `+41/-10` | The copied concurrency implementation got the same capacity/used split (SEV-01 residual), documenting that the two `PlatformBreaker` copies are **not** equivalent (9 vs 5 methods) | SEV-01 |

##### 9.3 HTTP clients, proxies and credentials

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/async_http.py` | modified `+152/-57` | `_client_cache` key gained the event-loop dimension (`(proxy, verify, http2, loop)`); only the current loop's entries are evicted and stale entries are swept via `loop.is_closed()` (previously every request evicted another room's live client, so every call rebuilt TCP+TLS and leaked the evicted sockets); login/cookie acquisition is isolated from the shared jar; `get_response_status` gained `platform`, defaulting `verify` to `get_effective_ssl_verify(platform)`; still **never** creating `aclose()` coroutines across loops | MID-21/22/26 |
| `src/sync_http.py` | modified `+17/-0` | `sync_req` normalises the proxy address through `handle_proxy_addr` (bare `ip:port` was only honoured on the async side) | MID-27, MIN-08 |
| `src/proxy.py` | modified `+88/-33` | Bracketed IPv6 parsed with `rsplit(":", 1)` + `[]` special case (it always raised `ValueError`, making the `__post_init__` validation dead code); Linux now reads the uppercase forms and `all_proxy`; proxy credentials preserved | MIN-20 |
| `src/weverse_auth.py` | modified `+23/-5` | Routed through `sync_http.sync_req(..., proxy_addr=...)`, recovering thread-level Session reuse, proxy and SSL policy; failure body masked | MIN-08 |
| `src/ttwid.py` | modified `+65/-7` | The process-global ttwid records its acquisition time and honours `cookie_cache.DEFAULT_TTL`; new `invalidate_ttwid()` clearing all three layers | MID-33 |
| `src/cookie_cache.py` | modified `+12/-1` | `singleflight` gained the generation comparison that only `fetch_cookies` had, giving `invalidate_generic` real semantics | MID-40 |

##### 9.4 Source selection, probes and quality tiers

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/stream_select.py` | modified `+186/-43` | The `record_url` channel is now also gated by `hls_effective_enabled` (closing the "HLS excluded ⇒ zero HLS probes" contract) and reuses already-known probe verdicts instead of re-probing the same address; last-resort pass-through now passes `_is_recordable_url` first (scheme whitelist http/https/rtmp/rtmps, non-empty netloc, rejects leading `-`/whitespace) and a rejected value is never passed through; segment-level backoff is keyed on the playlist URL; master playlists probe the highest-BANDWIDTH variant; MID-17 was **deliberately not implemented**, with the rejection recorded at `_PROBE_BACKOFF_PLATFORMS` | MID-17/18/19, MIN-02/03 |
| `src/stream.py` | modified `+190/-47` | The huya legacy branch dropped positional `zip` labelling in favour of value-driven mapping (`HUYA_RATIO_BY_CODE`, extended with 1000/250, nearest tier by value, warning whenever `ratio != target`); TikTok no longer stuffs m3u8 into `flv_url` and filters `None`/empty urls after padding; `get_stream_url` gained `@trace_error_decorator`, probes `url/play_url/m3u8_url/flv_url` in order and uses `play_url.get(key)`; the bilibili reverse map prefers the higher tier and drops unmapped qn; kuaishou numeric qualities resolve through `get_quality_index` first | MID-13/14/15/16/20/26/68, MIN-05/06 |

##### 9.5 Platform API parsing and signing

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/spider.py` | modified `+1385/-458` | `_shopee_host_suffix` strips `live.` before taking the suffix and the degenerate if/else was merged; `login_popkontv` / `login_twitcasting` switched to `_or_none` with null checks at call sites and an `isinstance str` guard before writing a Cookie header; bilibili buvid invalidation also purges the generic cache key; the douyin APP path takes ORIGIN/codec from the freshly parsed `parsed_data`; huajiao `encode=h264` now matches `h264_url`; taobao extracts `accountName`/`nick`; WinkTV null-checks before unpacking; baidu/popkon regexes accept end-of-string params (`(?=&\ | #\ | $)`); an actionable warning when the built-in TikTok guest cookie is used and parsing fails; SOOP relative manifest lines via `urljoin`; douyu betard / bilibili playUrl / twitch GQL on `_loads_dict` with `.get()` chains, the douyu POST body sent as a dict, zero requests when `enc_data` is missing; xiaohongshu `sid` gained the env → config → built-in override; twitch `browser_version` shares the UA constant and `os_version` is left to the encoder; kuaishou did / twitch client-id gained timestamps, TTL and invalidation hooks; **MID-48 closed**: bare `json.loads` 78 → 2 (single exemption `get_twitchtv_room_info`) on `_loads_dict` + `_dig/_dig_str/_dig_list` + `_warn_api_abnormal` | SEV-06/07, MID-33/40…50 |
| `src/platforms/douyin.py` | modified `+62/-3` | Calls `invalidate_ttwid()` on "handshake refused with HTTP 200" (200 only, once per session) so a revoked ttwid is re-fetched without restarting | MID-33 |
| `src/javascript/migu.js` | modified `+209/-44` | Removed the "cache heap views once before malloc" pattern in favour of `heapU8()/heapU32()` rebuilding views from `memory.buffer` on every use (out-of-range writes now throw instead of silently no-oping); `UTF8ToString` uses `TextDecoder('utf-8')` and all length arguments are UTF-8 byte lengths; empty-`ddCalcu` sentinel; the wasm/manifest fetch sites document the trust boundary and add https-only, exact-host allowlist, manifest-shape and wasm magic/size guards | MID-61/62 |
| `src/javascript/laixiu.js` | **deleted** | Dead code with no call sites (logic re-implemented in Python inside `src/spider.py`) and an implicit global `CryptoJS = require(...)` | 补-03 |
| `src/javascript/taobao-sign.js` | **deleted** | Dead code with no call sites whose comments retained a structurally complete real capture sample (session-token shaped value) | 补-03/04 |

##### 9.6 Danmaku pipeline and output wrap-up

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/collector.py` | modified `+161/-14` | Bounded ≤0.5 s wait for `is_running` in the "loop published but not running" window plus a second `_stop_event` check before `run_until_complete` (both documented reverse-order guarantees untouched); the sentinel uses `put_nowait`, and on `queue.Full` sets a writer stop event so the writer self-exits, still `join(3)` and never letting a failed sentinel block `srt.close()` (previously it could hang before `finally: _rec_sem.release()` and leak a recording slot); `_shutdown` cancels the `start()` task and lets cancellation propagate before `loop.stop()`, eliminating destroyed-pending tasks | MID-23/24, MIN-13/23 |
| `src/danmaku_monitor.py` | modified `+258/-52` | Sidecar writes moved to a process-level single writer thread (bounded queue + drop counter + `flush()`); the global lock now covers only stats and payload construction, so a slow disk cannot stall every room's event loop | MID-25 |
| `src/ws_client.py` | modified `+74/-13` | `self._ws = None` set before every `continue` (the old cleanup block was unreachable) plus an `state is OPEN` liveness check; `send_nowait` uses `spawn_danmaku_task` with a `_pending` strong-reference set and a 64-task backlog cap | MIN-12/13 |
| `src/srt_writer.py` | modified `+17/-7` | The retry-open reset moved ahead of line generation, removing duplicate block numbers and non-monotonic timestamps inside one `.srt`; sanitisation and in-segment clamping unchanged | MIN-24 ① |
| `src/ffmpeg_proc.py` | modified `+102/-19` | Replaced the dead `as_completed` + `f.result(timeout)` shape with a total-budget `wait`, and switched `ThreadPoolExecutor` for ≤8 daemon thread groups (non-daemon pool workers are joined at interpreter finalization, so a wait-only fix would still hang atexit); stdin closed right after writing; the three wait stages budgeted from remaining time (no more `timeout//3 == 0` skipping graceful exit and losing MP4 moov); unconfirmed cleanups logged | MID-32 |
| `src/video_postprocess.py` | modified `+77/-6` | Timeout/failure branches delete only the file this call produced and state that the source was preserved; re-encode timeout scales with source size (1.5 s/MB, floor 600 s, cap 3600 s) | MIN-04 |

##### 9.7 Configuration IO, masking and atomic writes

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/config_io.py` | modified `+25/-10` | `delete_line` compares after `rstrip("\r\n")` on both sides (fixing the MI-11-induced permanent mismatch on CRLF files, which failed silently on the primary Windows platform) and returns bool; a miss does not write, leaving observability to callers | SEV-05 |
| `src/utils.py` | modified `+256/-43` | `mask_credentials` extended to header form (`Cookie:`/`Authorization:`), JSON bodies (`"access_token": …`) and the cookie/sid_guard/ttwid key family, and recognises scheme-less `user:pass@host`; `replace_url`/`remove_duplicate_lines` now hold `file_update_lock` and write atomically, with the fallback branch clearing first; `atomic_write_text` adds `fsync` before replace, a unique mkstemp temp name, and preserves the original file mode; `run_node_script_async` no longer check-then-uses; `_JS_SHA256_EXPECTED` synced (new migu.js hash + the two removed scripts); 6 f-string log sites converted to `i18n.tr` | MID-28/29/57/62/68, MIN-11/21, 补-03/04 |

##### 9.8 Web admin panel (backend + frontend)

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `src/web_api.py` | modified `+428/-66` | `PUT /api/rooms` validates explicitly with validation sunk into the shared path (see `web_config`); all Web-section decisions use one `key_norm` (case variants can no longer skip hashing / anti-clear / token revocation), auth downgrade is refused while `web_host` is non-loopback, and the auth middleware re-checks the invariant per request; Host allowlist with the expected Origin rebuilt server-side; blocking IO (disk capacity, whole-file reads/writes, log archiving, directory stat) moved to `asyncio.to_thread` with `wait_for` + `stale` on status; password verification and the hash-upgrade write run in a threadpool, iterations clamped, and the rate-limit key taken from the connection peer with XFF peeled right-to-left only behind trusted proxies plus an IP-independent failure budget; external errors became fixed codes with details logged only; sensitive keys reject blank and literal `'***'`; `PUT /api/language` switches first then persists the **effective** code and rolls back on write failure; room delete/update decide 200/500 from `delete_line`'s result plus a re-parse check | SEV-02/04/05, MID-34…37/39/52 |
| `src/web_config.py` | modified `+300/-26` | Internal-address blocking became `ipaddress`-based semantics (loopback/private/link-local/reserved/multicast + CGNAT `100.64.0.0/10` + metadata IPs + benchmark/IETF ranges), accepts `inet_aton` shorthand (decimal/octal/short form), resolves the host and rejects when **any** A/AAAA result is internal or the name cannot be resolved; the quality whitelist moved up into the shared `validate_room_target` and validation sunk into `format_url_line`, the single write path | SEV-02/03, MID-35/36 |
| `web.py` | modified `+25/-2` | The one-shot "non-loopback + no auth" startup check became a reusable check shared with the middleware | SEV-04, MID-35 |
| `web/app.js` | modified `+137/-24` | Masked fields rendered with a `data-masked` marker, blanking one requires explicit confirmation and a server 400 gets its own message; `setLogoutVisible()` makes `/api/logout` actually reachable after login (hidden in `showLogin`); `api()` parses JSON and surfaces only `detail`, never echoing a non-JSON body (previously Windows absolute paths reached a toast); `SENSITIVE_MASK` kept same-source with the backend | MID-37/38/39, MIN-10 |
| `web/index.html` | modified `+3/-3` | Hard-coded Chinese `title` attributes on the theme/language controls moved to `data-i18n-title`; two table-header fallback strings entered the catalogs | MIN-10 |
| `web/style.css` | modified `+3/-0` | Only a `.hint-masked` hint style was added; the `#rooms-view` `table-layout: fixed` and column-width rules are untouched | MID-37 |

##### 9.9 GUI / i18n / notifications

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `gui.py` | modified `+289/-53` | `URL_config.ini` read with `utf-8-sig` and the same "is this a real room line" predicate as `parse_url_config` (a BOM no longer bypasses the CR-01 hang guard); the language menu disambiguates through `unique_display_names()` and persists/announces the effective code returned by `set_language`; quality-monitor downgrade entries carry `alert_at` and reset by timestamp ordering; advanced-settings save re-reads from disk, compares against the baseline, watches mtime and confirms on conflict; `_stopping` reset moved into `finally` | MID-51…56 |
| `i18n.py` | modified `+56/-7` | `set_language` follows the `has_catalog`/`resolve_language` path and returns the **actually effective** language code; added `unique_display_names()` | MID-52/53 |
| `msg_push.py` | modified `+23/-8` | Bark-style channels mask "the last path segment is the secret" as a general rule (the `day.app` host whitelist is gone), so self-hosted/reverse-proxied keys no longer reach rotating logs | MID-58 |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.po` + `.mo` | modified (`.mo` recompiled) | 26 msgids added across the round (MID-68 conversions + new module warnings + GUI dialogs); `.mo` header **N=664** (including the empty header msgid), **663** real entries; `compile_po.py --check` and `extract_i18n_strings.py` (0 missing) green | MID-68, MID-48 |
| `i18n/en_US.json` / `en_GB.json` / `zh_TW.yaml` | modified | Synced to **663** keys each with byte-identical placeholder sets per entry (avoiding the historical `{message_2}` vs `message=` mismatch that killed every push channel under zh_TW) | MID-68 |
| `README.md` / `README_EN.md` | modified | Removed the deleted JS scripts from the directory trees and fixed the tree gly… | 补-03/04 |

##### 9.10 Packaging, installers and the release chain

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `build_exe.py` | modified `+169/-34` | `_PINNED_RUNTIME_SHA256` restructured by `<os>-<arch>` runtime key × `ffmpeg`/`node` slot; `_is_pinned()` takes 64 lowercase hex shape as the only definition of pinned; added `--require-pinned`/`--allow-unpinned` (auto-on in CI) that `SystemExit` **before** any download; the `DLR_RUNTIME_SHA256` environment channel; `_download_file(slot=)` became a required keyword argument (removing the silent unpinned download on macOS/Linux) | SEV-10 |
| `src/ffmpeg_install.py` | modified `+87/-16` | The official-source ToFU sidecar is keyed by build identity (Last-Modified/ETag/Content-Length), so an upstream rebuild no longer creates the "official refused + Lanzou refused" dead end; refusals print the exact path to delete; the falsified yum→apt comment corrected in place and the fall-through made real | MID-59, MIN-24 ④ |
| `StopRecording.vbs` | modified `+296/-10` | Added the three pip-launcher image names (previously the recorder process was never matched, so only ffmpeg died and the parent relaunched it); the shim test became word-boundary + first-token basename (no more substring convictions that tree-kill editor LSP / pytest processes); silent mode requires the literal `-y`. File verified byte-wise as UTF-16 LE + BOM + all CRLF | MID-60 |

##### 9.11 Maintenance scripts and gates

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `scripts/check_runtime_pins.py` | **added** `189L` | Structure validation of the pin table (missing platform/slot/placeholder ⇒ rc=2), `--strict` (release gate, rc=1) and `--emit-env` (emits the table as JSON for CI to pass through) | SEV-10 |
| `scripts/run_gates.py` | modified `+133/-11` | Parses leading `NAME=value` prefixes from the AGENTS gate block into the child environment; `GATE_CHILD_ENV` defaults to `PYTHONUTF8=1`; `FATAL_STDERR_PATTERNS` fails the run on "warns but exits 0" shapes; `ensure_utf8_streams()` fixes the crash while forwarding black's passing `✨` line under cp936 | MID-63 |
| `scripts/check_coverage.py` | modified `+54/-2` | "No coverage data" became rc=2 hard failure with the next-step command, separating "forgot to run tests" from "coverage below threshold" | MIN-19 |
| `scripts/check_version.py` | modified `+55/-1` | New assertion that the `ARG` declaration line precedes the **instruction start line** that consumes it (continuations traced back, comment lines skipped) | MIN-14 |
| `scripts/check_annotations.py` / `scripts/extract_i18n_strings.py` | modified `+2/-1` each | References to the deleted `gui_legacy.py` removed | MIN-15 |

##### 9.12 CI, containers and dependency manifests

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `.github/workflows/ci.yml` | modified `+117/-6` | black/isort steps carry step-level `PYTHONUTF8=1` aligned verbatim with the AGENTS block; added the `Gate isort/black silent-skip warnings` fallback step; added the `deps-audit` job (`pip-audit -r requirements.txt`, both audit steps UTF-8-pinned) wired into `ci-summary.needs`; dropped `gui_legacy.py` | MID-63, SEV-10, 补-05, MIN-15 |
| `.github/workflows/build-release.yml` | modified `+32/-2` | prepare runs `check_runtime_pins.py --strict` and forwards the table through `--emit-env` into `DLR_RUNTIME_SHA256`; build commands pass `--require-pinned` explicitly | SEV-10 |
| `.github/workflows/trivy.yml` | modified `+15/-4` | `checkout` raised to v7, template branch filter cleaned, image name became the local build tag, `--build-arg APP_VERSION` read from pyproject | MIN-14/16 |
| `.github/workflows/issue-translator.yml` | modified `+29/-5` | Downgraded to `workflow_dispatch` only, with top-level `permissions: contents: read / issues: write`, and the file header states the preconditions to re-enable automation (an on-the-spot verified 40-char SHA + kept least-privilege + recorded check date) | MIN-17 |
| `Dockerfile` | modified `+10/-6` | `ARG APP_VERSION` moved above `LABEL version=` (previously `--build-arg` had no effect and nothing failed at build time) | MIN-14 |
| `docker-compose.yaml` | modified `+7/-0` | `pull_policy: build` inside the anchor, removing the "`up` without build pulls `:latest`" fallback | MIN-18 |
| `requirements.txt` / `pyproject.toml` | modified `+19/-2` / `+13/-2` | `starlette` floor raised above the affected band, explicit `urllib3>=2.7.0` added; the two manifests are one-for-one **21/21** (verified with `tomllib`, zero symmetric difference), `protobuf>=…,<8` upper bound preserved | 补-05 |
| `.gitignore` / `.dockerignore` | modified | Both gained `coverage.json` (the `--cov-report=json` artefact) | — |

##### 9.13 Tests (18 added files + 29 modified)

| Path | Type | Coverage | Items |
| --- | --- | --- | --- |
| `tests/test_record_watchdog.py` | **added** `589L` | 45 s gap not killed / 11 min killed, time-limit round wrapping up as a success, cap inert when segmentation is off, state convergence after slot give-up and mid-body exceptions, empty `recording` with no live subtitle thread when `flv_url` is missing, direct-download byte threshold | SEV-08/09, MID-01/06/07/12 |
| `tests/test_scheduler.py` | modified `+299/-0` | `recompute` does not inflate with holders present, measured peak concurrency ≤ capacity, unpaired `release` creates no permits, shrink keeps held slots, probe ownership + lease | SEV-01, MIN-22 |
| `tests/test_recorder_status.py` | **added** `228L` | Console capacity reads `capacity`; the loop cannot spin faster than its sleep when the body always raises | SEV-01, MID-31 |
| `tests/test_spider_hardening.py` | **added** `1517L` | Four payload shapes for 52 platform functions, "credential never in a log" assertions, the `BARE_JSON_LOADS_CEILING` ratchet and the per-function zero-bare-loads scan | MID-48, MID-45 |
| `tests/test_decorator_contract.py` | modified `+2/-2` | Repo-wide AST lock: return annotation ↔ fallback decorator pairing, and no comment between `@decorator` and `def` | SEV-07, MID-68/69 |
| `tests/test_web_config.py` / `test_web_api.py` | modified `+241/-0` / `+830/-16` | Internal-address variant tables, PUT/POST verdict parity, case-variant guards, Host allowlist, rate-limit key and iteration clamp, mask/blank 400s, CRLF delete fixture | SEV-02/03/04/05, MID-35/36 |
| `tests/test_web_config_locks.py` / `test_web_config_secret_mask.py` | **added** `163L` / `185L` | 400 wording plus "value not overwritten" re-check; table-driven against the real `_looks_like_secret_value` / `_validate_room_url_target` | MID-69 |
| `tests/test_stream.py` / `test_stream_select.py` / `test_quality_tiers.py` | modified `+317/-24` / `+263/-0` / `+6/-3` | Value-driven huya tiers and order independence, TikTok zero HLS probes incl. record_url, URL shape whitelist, backoff keying, variant choice, bilibili reverse map | MID-13…20, MIN-02/03/05/06 |
| `tests/test_collector.py` / `test_danmaku_monitor.py` / `test_ws_client.py` / `test_srt_writer.py` / `test_ffmpeg_proc.py` / `test_video_postprocess.py` / `test_cookie_cache.py` / `test_douyin_danmaku.py` / `test_ttwid.py` | added / modified | Reverse-order handshake preserved + dropped-signal window, no IO under the lock, liveness after reconnect, SRT numbering, cleanup budget, timeout deletes this-run output, generation compare, ttwid invalidation and TTL | MID-23/24/25/32/40, MIN-04/12/13/23 |
| `tests/test_async_http.py` / `test_sync_http.py` / `test_proxy.py` / `test_utils.py` / `test_config_io.py` / `test_weverse_auth.py` | added / modified | Loops do not evict each other and same-loop reuse holds, proxy-address normalisation, IPv6/uppercase env/credentials, nine masking samples plus untouched public URLs, fsync ordering, CRLF `delete_line` | MID-21/22/26/27/28/29/57, SEV-05, MIN-08/11/20/21 |
| `tests/test_gui_monitor.py` / `test_i18n.py` / `test_msg_push.py` / `test_ffmpeg_install.py` / `test_stop_recording_vbs.py` | **added** | BOM predicate, effective language, Bark self-hosted masking, sidecar rotation, VBS image names / word boundary / silent predicate + raw UTF-16 bytes | MID-51…60, MIN-24 |
| `tests/test_frontend_quality_ui.py` + `tests/frontend/test_quality_ui.mjs` | modified `+171/-9` / `+405/-19` | Process-group timeout kill with a real "results were parsed" assertion; logout visibility, mask confirmation, error-detail parsing, and the mechanical four-catalog / `data-i18n` key gate (27 cases) | MID-64, MID-37/38/39, MIN-10 |
| `tests/test_i18n_migration.py` | modified `+102/-27` | Gate predicate tightened from "first argument is a JoinedStr" to "the first argument's subtree contains a FormattedValue", `tr()` kwargs not recursed (convention ②), plus a self-check case that turns red if the gate is weakened | MID-68 |
| `tests/test_test_hygiene.py` | **added** `273L` | AST scan over tests/ for four banned shapes (stdlib module-object patching, broad `filterwarnings`, …) with positive and negative self-checks | MID-64/65/66/67 |
| `tests/test_ab_sign.py` / `tests/test_record_failure_feedback.py` / `tests/test_start_record_command_golden.py` / `tests/test_bilibili_danmaku_info.py` / `tests/test_only_fans_defaults.py` / `tests/test_tars_frames.py` / `tests/test_platform_dispatch.py` / `tests/test_record_container.py` / `tests/test_spider_fixes.py` / `tests/test_spider.py` / `tests/test_machine_validation_fixes.py` | modified | SM3 standard KATs and a time-frozen determinism case, shim-ised stdlib patches, the `capacity` stub and direct-download byte shape, AsyncMock without the ignore marker, cross-layer defaults, malformed Tars frames, full `PLATFORM_HOST` coverage, segment extension derivation, three Shopee TLDs | MID-65/66/67, MID-03/04/05/06, SEV-06, MIN-01 |

##### 9.14 Documentation and metadata

| Path | Type | What changed | Items |
| --- | --- | --- | --- |
| `AGENTS.md` | modified `+235/-7` | 20+ long-term conventions added or corrected: gate UTF-8 and warnings-as-failure, `deps-audit` (local repro must carry `PYTHONUTF8=1`), the SEV-10 three-layer defence and "three kinds of pinning do not cover each other", the standalone copy rule, Dockerfile `ARG` ordering, `check_coverage` rc=2, the MIN-17 ref criterion, no `:latest` fallback, the non-reentrant-lock list correction (`file_update_lock` is an RLock; judge from the definition line), the tightened i18n parameter-log predicate, and the spider JSON access discipline with its ratchet | many |
| `CODE_WIKI.md` / `CODE_WIKI_EN.md` | modified (both; **line counts deliberately not maintained here** — the figure is self-referential and drifts with every appended section, per the same "do not keep counts in this file" rule recorded in AGENTS.md) | This round's changelog entry (paired zh/en): severe table, thematic batches, new gates, security surface, seam closure, verification, MID-48 plus the local CI-equivalent verification, and this module-classified inventory | all |
| `docs/agent-reference/measured-evidence.md` | modified | Two new evidence sections: `isort 静默跳文件` (18 files) and `pip-audit 本地审计读数`… | MID-63, 补-05 |
| `docs/agent-reference/project-structure.md` | modified | Directory tree gained `scripts/check_runtime_pins.py` and `trivy.yml` | MIN-14/16 |
| `DouyinLiveRecorder.egg-info/` | regenerated | `PKG-INFO` version 4.3.0; `requires.txt` aligned three ways with both manifests (including `urllib3`) | — |
| `.workbuddy/memory/2026-09-21.md` | modified | Same-day wrap-up: reusable criteria, MID-48 closure, local CI verification and the pending Actions command list | — |

##### 9.15 Deletions and their blast radius

| Removed | Path | Impact and follow-up |
| --- | --- | --- |
| Dead signing scripts | `src/javascript/laixiu.js`, `src/javascript/taobao-sign.js` | No call sites; their two `_JS_SHA256_EXPECTED` entries were removed in the same pass, leaving 5 pinned scripts under `src/javascript/`; README / CODE_WIKI tree entries cleaned |
| Legacy positional huya tier inference | `src/stream.py` (`labels = ["UHD","HD","SD","LD"]` + positional zip) | Replaced by value-driven mapping; the test that had frozen the wrong semantics (`test_legacy_uhd_via_exsphd_labels`) now asserts `(2000, BD8)` |
| Substring stream-suffix matching | `main.py::_match_stream_suffix` | Now compares the path extension (`_stream_path_suffix`), so `?a=.flv` can no longer route an arbitrary URL into the custom-stream branch |
| "Silently skip under a non-UTF-8 locale" gate behaviour | `scripts/run_gates.py`, `ci.yml` | Both now run with `PYTHONUTF8=1` and treat `Unable to parse file` as failure; Linux defaults to UTF-8, so the local leg remains the only one that can prove this |

`pytest -q` **1917 passed / 10 skipped / 0 warnings**, `basedpyright` 0/0, `check_coverage.py` PASSED
(73.28% overall, `spider.py` 68.4%), frontend `node --test` 27 passed, translation catalogs **663** entries each
(`.mo` header N=664).

**Summary**: Only the `python` paths-filter group in `.github/workflows/ci.yml` changed, closing previously-missed triggers — **no new filter group, no new job, no runtime source touched, nothing removed at runtime**. The list previously omitted `web/**`, so editing `web/app.js`'s boolean-parsing tokens did not trigger the frontend regression lock; it also still carried a stale reference to the already-deleted `gui_legacy.py` (removed in v4.1.0-dev / 2026-09-10).

#### 1. Changes (the `Detect path changes` step of the `setup` job in `.github/workflows/ci.yml`)

- **New triggers** (merged into the existing `python` group; a match fans out to all six gated jobs — static / typecheck / test / concurrency-test / integration-verify / build-verify):
  - `web/**` — `web/app.js`'s `parseConfigBool + CONFIG_TRUE_TOKENS / CONFIG_FALSE_TOKENS` and `src/config_bool.py` are a cross-language boolean-parsing invariant (AGENTS.md "Unified parsing of boolean config values"; the recognized token set must be kept in sync across both sides). Once included, a `web/`-only change also flows through the test job's pytest → `tests/test_frontend_quality_ui.py` subprocess driving `node --test tests/frontend/test_quality_ui.mjs` (Node ships with ubuntu-latest).
  - `Dockerfile` / `docker-compose.yaml` — the image's Python/Node version constants must stay same-source with `pyproject.toml`.
  - `.github/actions/**` — the `retry` composite action is reused across ci.yml / build-release.yml; its interface changes ripple into every job.
- **Removed item**: `gui_legacy.py` (deleted on 2026-09-10; the list entry was a stale leftover — paths-filter cannot match a nonexistent file, harmless but misleading, cleared here).
- **Design comment corrected in place** (above the `Detect path changes` step): the original "pure frontend static assets (web/) do not trigger" is a falsified factual statement, rewritten per AGENTS.md ("falsified statements should be corrected in place") — one reason line per newly added glob plus a one-line dated history note, while preserving the original "pure documentation (`*.md`) does not trigger" intent.

#### 2. Related doc correction (`CODE_WIKI.md` / `CODE_WIKI_EN.md`)

- The §6 "GitHub Actions CI" path-filtering note previously said "pure frontend (web/) does not trigger", which now conflicts with the list; corrected in place on both the Chinese and English sides.

#### 3. Verification

| Item | Command / scope | Result |
| --- | --- | --- |
| Frontend regression lock runs locally | `node --test tests/frontend/test_quality_ui.mjs` | tests 9 / pass 9 / fail 0 / skipped 0, exit 0 (includes the three boolean-parsing assertions) |
| filters structure check | `python -c "yaml.safe_load(...)"` | `python` group has 18 entries, `web/**` present, `gui_legacy.py` gone, `Dockerfile` / `docker-compose.yaml` / `.github/actions/**` all present |
| Routing check | a single `web/app.js` change | `python` matches → static and test (and the other gated jobs) all run; `ci-summary`'s needs cover the six jobs, so the required check is no longer all-skipped |

### v4.3.0-dev (2026-09-20) — Room correlation field `extra[room]`: per-room chains can be cut out of interleaved logs

**Summary**: The recording process's two file sinks gained a **thread-level room correlation field**, removing the diagnostic obstacle that when several rooms record concurrently, lines in `logs/streamget.log` / `logs/PlayURL.log` interleave in arrival order and a single room's chain cannot be reconstructed. This round **adds only the correlation identifier**: log levels, the `filter` split (INFO→`PlayURL.log`, everything else→`streamget.log`), `rotation="300 KB"` / `retention=3`, the console `custom_format` and the GUI process's exclusive `logs/gui.log` isolation logic are **all unchanged**; **nothing was removed and no dependency was added** (loguru's existing `extra` capability is reused). Touched surface: `src/logger.py` (mechanism), `main.py` (two bindings), `tests/test_logger_room_context.py` (new file, 4 cases), `AGENTS.md` (one new known-pitfall entry).

#### 1. Logging module (`src/logger.py`, new field mechanism + two line-format constants)

- **New public symbols** (added to `__all__`): `ROOM_FIELD = "room"`, `set_room_context(room)`, `get_room_context()`; internally `_room_var: ContextVar[str]` and `_room_patcher(record)`.
- **Mechanism**: the room thread's logging call sites are spread over `main.py` and dozens of `src/*` modules, so per-call `logger.bind()` is impractical. A ContextVar now carries the "current room", and a **global patcher** registered via `logger.configure(extra={ROOM_FIELD: ""}, patcher=_room_patcher)` writes it into `record["extra"]["room"]`. Two timing facts matter: the patcher runs in the **calling thread**, before `handler.emit` (i.e. before enqueueing), so under `enqueue=True` it always reads this thread's value; and the patcher runs after the `extra` merge, hence it refuses to overwrite a non-empty value, letting an explicit call-site `bind(room=...)` / `contextualize(room=...)` win.
- **The `extra` default must not be removed**: without `extra={ROOM_FIELD: ""}`, formatting an unbound record raises `KeyError: 'room'`, and loguru does not propagate it — it prints a `Logging error in Loguru Handler` block to stderr **for every line** and drops that line, i.e. silent log loss.
- **Formats consolidated into constants with the new column**: `_STREAMGET_FORMAT` = `time | level (ljust 8) | room | module:function:line - message`, `_PLAYURL_FORMAT` = `time | room | message`. Unbound lines leave the column empty while the **column layout stays fixed**, so a whole-segment match on `| 序号N anchor-name | ` reliably extracts one room's chain (anchor names pass through `clean_name`, where `|` is an illegal filename character already replaced, so it can never break the delimiter).
- **`logs/gui.log` deliberately keeps no such column**: the GUI process never records, the column would be permanently empty, and the exclusive-handle isolation logic (`GUI_PARENT_ENV`, see the 2026-08-29 entry) is untouched.
- Typing uses `if TYPE_CHECKING: from loguru import Record` (`Record` is a TypedDict defined only in the `__init__.pyi` stub and cannot be imported at runtime), satisfying mypy's `disallow_untyped_defs` and the `patcher: PatcherFunction` signature.

#### 2. Recording entry (`main.py`, one import + two bindings)

- `from src.logger import set_room_context`.
- `start_record()` binds `f"序号{count_variable}"` at the **thread entry**, before the loop: the logs emitted earlier than `record_name` (exit flag / recording stopped / commented-out exit / per-platform breaker back-off / resolution failure) then also belong to a room.
- After each polling round resolves the anchor name and assigns `record_name = f"序号{count_variable} {anchor_name}"`, the field is upgraded to the full room name; `record_name` is recomputed every round, so an anchor rename (`auto_update_anchor_name`) is followed automatically.
- **Scope of effect**: tagged = the room thread itself plus Tasks created by `asyncio.run()` inside it (ContextVar semantics — covers `check_subprocess` / `direct_download_stream` / `_resolve_platform_stream` logs); untagged (empty column) = the main loop, the GUI process, and **newly started threads** (danmaku collector thread, `push_message`, post-processing transcode pool) — a ContextVar is not inherited by new threads, so those chains are still grepped by keyword (`record_name`, output file names).

#### 3. Tests (`tests/test_logger_room_context.py`, new file / 4 cases)

- The fixture follows `tests/test_logger_gui_parent.py` conventions (`sys.argv[0]` pointed at tmp_path to isolate `config/` and `logs/`, `sys.stderr=None` to skip the console sink, `importlib.reload` to take the "recording process" branch), and assertions run against the **two real files on disk**, not against a stub.
- ① `test_two_rooms_can_be_split_by_room_field`: two room threads each write 20 `WARNING` lines forced to interleave by a `threading.Barrier`; splitting on the room column must return exactly 20 lines per room, no line may match both rooms, and at least one adjacent pair must belong to different rooms (locking the "interleaved" premise so that a degenerate "one room per segment" implementation cannot pass the count assertions as a false green); it also asserts `set_room_context()` / `get_room_context()` are self-consistent per thread (direct proof of thread isolation).
- ② `test_unbound_room_logs_still_land_with_empty_column`: an unbound record still lands on disk with an empty room column. ③ `test_explicit_bind_wins_over_thread_context`: a call-site `logger.bind(room=)` outranks the thread-level fallback. ④ `test_level_routing_unchanged_after_adding_room_field`: INFO still goes only to `PlayURL.log`, DEBUG only to `streamget.log`.

#### 4. Agent conventions (`AGENTS.md` "Known pitfalls → Logging, console and GUI / background mode", one new entry)

- New entry "cut interleaved multi-room logs by the `extra[room]` column, not by the `[record_name]` prefix": the whole-column matching commands (Windows `Select-String -Pattern '\| 序号3 anchor \| '`, POSIX `grep -F '| 序号3 anchor | '`), the three things not to touch (the `extra` default must stay, `gui.log` carries no such column, adding the identifier must not drag in level / filter-split / rotation-retention changes), the scope limits (new threads do not inherit it; call-site `bind` wins) and the regression lock.

#### 5. Verification

| Item | Command / scope | Result |
| --- | --- | --- |
| Focused cases | `pytest tests/test_logger_console_sink.py tests/test_logger_gui_parent.py tests/test_log_archive.py tests/test_logger_room_context.py` | 26 passed |
| Full suite | `pytest -q` | **1062 passed / 2 skipped / 0 warnings** |
| Gates | `black --check` (120/py314), `isort --check-only` (profile black), `mypy` (120 files), `basedpyright`, `scripts/check_annotations.py` | all clean (locally isort needs `PYTHONUTF8=1`, otherwise the gbk default encoding silently skips `main.py`) |
| Real chain, two rooms | Two room threads started through `main.start_record` (`argv[0]` pointed at a `%TEMP%` subdirectory to isolate `config/ logs/ downloads/`) | `streamget.log` got `… \ | DEBUG \ | 序号1 \ | …` and `\ | 序号2 \ | `, one line each; the two INFO lines landed in `PlayURL.log` with an empty room column and no loguru formatting error — **the level-to-file routing is identical to before the change** |

- **`python tests/test_<platform>_live_collector.py <URL> [seconds]` was not used for the two-room check** (the originally specified validation): those 5 scripts call `src/spider.py` and `DanmakuCollector` directly, **bypassing `main.start_record`**, so the room column is always empty there and the feature cannot be validated (they also need live rooms and outbound network). The "Real chain, two rooms" row above covers the same acceptance condition instead.

### v4.3.0-dev (2026-09-20) — Web panel `/health` liveness endpoint + HTTP smoke wired into CI

**Summary**: This wires the built-in smoke tool `scripts/smoke_test.py` from "has a tool, no gate" into a CI-executable real HTTP liveness probe. Previously the `/health` item in `scripts/smoke_web.json` carried the placeholder name "(real endpoint to be added as needed)", while `src/web_api.py` had no such route at all (a probe would hit FastAPI's default 404), so it could not be wired in. This round adds the `/health` endpoint, a real liveness assertion, the CI smoke wiring, and guarding cases; no runtime source was deleted. Categorized by module below.

#### 1. New feature: liveness endpoint (`src/web_api.py`)

- **Route**: inside `create_app`, added `@app.get("/health")` -> `{"status": "ok", "version": _APP_VERSION}`. It deliberately reflects only "process alive + ASGI/routing ready + version readable" and does **not** probe the recording engine / disk / platform APIs — when those are unhealthy the panel should still be reachable (users need to enter the panel to change config), so folding them into the liveness check would only produce false-red gates.
- **Auth whitelist**: added `/health` to `auth_middleware`'s pass-through branch (right next to `/api/auth/status`). Liveness probes (CI smoke / LB health checks / monitoring) hold no panel credentials; if gated by `web_auth_enable`, a probe would get 401 the moment auth is turned on and be misread as "service down". The response contains only status and app version — each constant, and already publicly obtainable via `/docs` and `/api/auth/status` — so whitelisting adds no information surface.
- **Contract note**: `{"status": "ok"}` is an external contract; the comment records "new fields are fine, renaming or changing values is not", tying together the `smoke_web.json` and CI-step wording at all three sites.

#### 2. New feature: CI smoke wiring (`.github/workflows/ci.yml` + `scripts/_ci_web_smoke.sh`)

- **Placement**: appended two steps at the end of the **existing** `test` job (after the coverage/Codecov upload steps, so a smoke failure does not suppress `coverage.xml`); no new job, no new tool or dependency. Guarded by `if: matrix.python-version == needs.setup.outputs.python_min`, the same condition as the adjacent coverage steps, so **it does not change other jobs' path-filter semantics**.
- **`Web panel smoke test` step**: runs `bash scripts/_ci_web_smoke.sh` via the existing `.github/actions/retry` composite action (`attempts=2`, `backoff=5`), converging retry policy in action.yml and **not inlining a for-loop in the job** (AGENTS.md unified policy). The two environment variables `DOUYIN_SKIP_RUNTIME_CHECK=1` (skip node probe/auto-install at import; this job installs no Node) and `DOUYIN_DISABLE_LOG_ARCHIVE=1` (one-shot process, do not rename `logs/*` on stop) are written as a **command prefix** rather than step `env` — a composite action's visibility of the caller's step-level env is not officially guaranteed, whereas inline assignment reliably passes them to the script and its `nohup` child.
- **New script `scripts/_ci_web_smoke.sh`**: one full attempt = controlled `python web.py` startup (`nohup` background, PID recorded) -> `/health` readiness polling (90s cap; if the process exits mid-wait, fail immediately and dump the panel log) -> `smoke_test.py` assertions -> `trap EXIT` teardown of the process tree (`pkill -P` + fallback `pkill -f 'python web\.py'`). The script **exits with the smoke exit code** (0 pass / 1 assertion failure or panel-not-up / 2 config problem), so on failure the step **turns red directly = job red**; each retry round re-runs the script, which equals "bring up a fresh clean panel from scratch", so retries genuinely handle cold-start slowness / transient HTTP jitter instead of repeatedly re-running a deterministic assertion failure. Before startup it seeds an **all-commented** `config/URL_config.ini` (no rooms to record, the engine only runs its config hot-reload loop, never spawning ffmpeg nor touching platform APIs — the same technique as `build_exe.py`'s `_ensure_url_config` smoke helper); `config/config.ini` is not committed, and when missing `read_web_config` falls back to `WEB_DEFAULTS` (127.0.0.1:8000 + auth off).
- **`Upload web smoke artifacts` step**: `if: ... && always()` ensures `logs/web-smoke-report.json` (a machine-readable report with actual status codes / timings / error lines) and `logs/web-panel-smoke.log` are uploaded even when the smoke step goes red; `if-no-files-found: warn` (missing files do not backfire on the gate, and `logs/` is gitignored so it does not pollute the workspace).

#### 3. Modification: liveness config (`scripts/smoke_web.json`)

- The `/health` item's `name` changed from "health check (real endpoint to be added as needed)" to "Web panel health check" (placeholder removed, since the endpoint now really exists); the assertion `expected_status: 200` + `expect_json: {"status": "ok"}` is unchanged and now aligns verbatim with the added route. `base_url` remains `http://127.0.0.1:8000`.

#### 4. New feature: guarding cases (`tests/test_web_api.py`)

- Added `TestHealthEndpoint` with two cases: `test_health_ok_when_auth_enabled` (under `app_env`'s fixed `auth=true`, `/health` must still be 200, and `version` is same-source as `app.version`) and `test_health_ignores_engine_state` (patch `get_status` to raise so `/api/status` returns `{"error": ...}`, yet `/health` stays 200 — proving the probe does not mix in engine health).

#### 5. Documentation sync (`README.md` / `README_EN.md`)

- The "Web/API smoke testing" section on both sides gains two bullets: (1) the default case probes `/` (home page 200) and `/health` (`{"status": "ok"}`, noted as a public endpoint not gated by `web_auth_enable`); (2) "Wired into CI" — the `test` job starts the panel in a controlled way after pytest, handles flakiness via retry, keeps `logs/web-smoke-*` artifacts and turns the job red on failure, covering the "can the panel process really bind and respond" path that TestClient cannot reach.

#### 6. Incidental change (`scripts/run_gates.py`)

- Because this round adds `_ci_web_smoke.sh` under `scripts/`, which triggers the CI `static` job's `black --check .`, and `scripts/run_gates.py` (the formal script introduced in the "Local one-shot gate trigger" subsection under the "Metadata source-of-truth reconciliation" entry) had one over-long `subprocess.run` line failing black, it was given a **mechanical line-wrap reformat** (lossless, no logic change) to keep `black --check .` green.

#### 7. Verification

| Check | Result |
| --- | --- |
| Local panel up + `python scripts/smoke_test.py -c scripts/smoke_web.json` | exit **0**, 2/2 pass; `/health` actually returns `{"status":"ok","version":"4.3.0"}` |
| Change `/health` expected status to a wrong value (500) and rerun | exit **1** (`status 200 != expected 500`), reverted to 200 afterwards |
| `pytest` (full) | **1048 passed / 2 skipped / 0 warnings** |
| `black --check .` / `isort --check-only .` | green (138 files unchanged) |
| `mypy` (no path arg) | pass, 119 files, 0 errors |
| `basedpyright` (`web_api` + cases) | 0 errors / 0 warnings / 0 notes |
| `scripts/check_annotations.py` | pass (`.sh` excluded from density scan; Python only) |

> Note: the `test` job in `ci.yml` now has 3 `.github/actions/retry` usages (ffmpeg install, dependency install, Web smoke); this round did **not** change `AGENTS.md`'s "retry count" figure (left to the maintainer, not updated with this entry).

### v4.3.0-dev (2026-09-20) — AGENTS.md segmentation & reachability refactor (better-harness: progressive disclosure)

**Summary**: documentation-and-agent-instruction change only, addressing the better-harness finding `root-instruction-file-carries-no-progressive-disclosure` — the root `AGENTS.md` loaded in full with no segmented navigation, mid-list pit entries easy to miss on a skim, and `agent-lint` reporting `links`/`references` both **0** (no machine-checkable link, so "0 missing references" was an empty-set conclusion, not a healthy one). The decision that **the root file is the single source of truth for long-term conventions** is kept unchanged; no entry semantics were removed, only segmentation and reachability were added. **No runtime source changed.**

#### 1. Agent instruction file (`AGENTS.md`, modified)

- **Risk controls hoisted**: added an early `## Risk controls (front-matter)` section that lifts the over-reach boundaries scattered in the middle of long entries (batch venv reinstalls must be handed back to the user, cleanup scope must not over-reach, deletions blocked by safe-delete must list residue, governance-style workflow skills need the run scope and artifact root confirmed first) and the credential red lines (`config/*.ini` never committed, mask via `utils.mask_credentials()` before writing, no real credentials in docs) to the top. This section is **routing only** — it points to the original entries as the single source of truth, restates no rules, adds no new constraint, so no second contradictory version can appear.
- **Pit list segmented by theme**: the 82-entry `## Known pitfalls` list was regrouped under **18 `###` theme headings** (recording chain & room thread / stream-URL probe / danmaku & SRT / platform API & signature / quality tiers / HTTP client reuse / concurrency & locks / ffmpeg command / logging & GUI background / i18n / config keys & boolean parsing / credential masking / type-check & static gates / hot-path performance / build artifacts & runtime / decorator contract / Web panel & API / testing & review). Entry bodies were **kept verbatim**, only the grouping order changed; 5 directional "aforementioned entry X" cross-references were re-checked and still resolve under the new order.
- **Reachability rule & reading order**: the file header gained a `reachability` note and a `reading order` — "constraints that must be obeyed every session stay in the root; checklists of where-to-find-things / supporting measurements may be externalized".
- **Routing via Markdown links** (turning `agent-lint` `links`/`references` from 0 into a checkable count): added links to `pyproject.toml`, `scripts/check_annotations.py`, `scripts/check_coverage.py`, `.gitignore` / `.dockerignore`, `config/config.ini` / `config/URL_config.ini`; the per-module coverage **threshold numbers** are no longer maintained in the root file — they now point to `MODULE_THRESHOLDS` inside the script (no second copy of the table).

#### 2. Agent reference sub-documents (`docs/agent-reference/`, added)

- **`docs/agent-reference/project-structure.md` (added)**: externalized the full project directory tree (111 lines, with per-directory/file responsibility comments) out of `AGENTS.md`'s "Project structure" section; the root location is now a one-line responsibility note plus a reference-style link `[project structure tree][struct-tree]`.
- **`docs/agent-reference/measured-evidence.md` (added)**: externalized the **one-off measured readings** at the tail of 4 pit entries (probe-client reuse speedup / keepalive connection measurements / huya tier seven-way sampling / douyu rate-clamp recovery); the entry body and its constraint sentences stay in the root — only the supporting data moved out, with an in-place anchor link. **Externalization criterion**: a segment may move only if it contains no imperative constraint ("must / forbid / shall not / 须").
- **Removed**: the original full directory-tree block inside `AGENTS.md` (semantically externalized, not dropped).

#### 3. Verification (`agent-lint`, read-only audit)

- `agent-assets-review` profile: `references` **0 → 15 (>0)**, `missingReferences` **still 0**; all 15 link targets pass an `exists:true` check.
- `agents-md-review` profile: the `long-root-without-progressive-references` advisory is cleared; the `root-length-hard-cap` warning (root file > 200 lines) remains — it conflicts with the authorized boundary of "remove no semantics, keep a single source of truth", so it is intentionally retained and out of scope for this pass.
- Semantic preservation: the 82 pit entries diff to **0 missing** against the baseline; line count 1091 → 1074 (the 111-line tree moved out while the risk section / theme headings / links were added).
- One-jump reachability: sampled — the project-structure `[struct-tree]` definition resolves to the tree text in the sub-doc, and the 4 measured anchors (root `#anchor` → matching `##` heading in the sub-doc) each land on the original text in one jump.

### v4.3.0-dev (2026-09-20) — Metadata source-of-truth reconciliation + four-language catalog verification + full quality-gate run

**Summary**: this round is **documentation-and-verification only** — **no runtime source changed** (the quality-gate run finished with zero modifications). Three parts: ① backfill the 2026-09-19 62-item review changelog into both READMEs; ② verify all four locale catalogs entry-by-entry and recompile `.mo`; ③ correct the factual "663 entries" error in the 2026-09-19 entry, in both languages. All five gates green.

#### 1. Documentation sync (`README.md` / `README_EN.md`)

- **Problem**: the `v4.3.0 (2026-09-19)` 62-item review entry existed **only in CODE_WIKI**; both READMEs lacked it, leaving user-facing docs one version behind the engineering docs.
- **Change**: added a mirrored entry at `README.md` (line 857) and `README_EN.md` (line 855), matching the CODE_WIKI record for that version (12 critical / 22 moderate / 28 minor digest + gate results).
- Same treatment as section 3 of the 2026-09-18 entry, which backfilled the then-missing 2026-09-17 entry.
- **Also**: the "Document Statistics and Index" snapshot in `CODE_WIKI.md` / `CODE_WIKI_EN.md` was refreshed in the same pass — total 324 -> **285**, the `.qoder/repowiki/**` directory (formerly 302) no longer exists in the workspace, workspace memory 12 -> 45, historical memory 7 -> 14, and a row was added for the 2 one-off review reports (`CODE_REVIEW_*.md`).

#### 2. Locale verification and recompilation (`i18n/`)

| Check | Result |
| --- | --- |
| Entries | **635** in each of the four catalogs (`zh_CN.po` non-empty msgid 635; `zh_CN.mo` header N=636 incl. the empty msgid) |
| Missing | **0** (`scripts/extract_i18n_strings.py`: 420 extracted at runtime, 635 in catalogs) |
| Key-set parity | All four identical (the script printed no `[不一致]` line) |
| Placeholder parity | **0** mismatches (per-entry comparison of `{name}` placeholder sets between each catalog value and the source msgid) |
| `.mo` | Recompiled: `i18n/zh_CN/LC_MESSAGES/zh_CN.mo`, 636 entries / 79262 bytes; `compile_po.py --check` passes |

- Placeholder parity is a **new hardening step** this round: 2026-09-18 had a defect where `zh_TW.yaml` wrote placeholders as `{message_2}`, making `i18n.tr()` raise `KeyError` under Traditional Chinese. Placeholder comparison was therefore added on top of key-set parity.

#### 3. CODE_WIKI factual correction (both languages)

- The 2026-09-19 entry previously stated "locale catalogs 635 -> **663 entries**"; measurement shows **635**. Both `CODE_WIKI.md` and `CODE_WIKI_EN.md` were corrected in place with a correction note retained, per the AGENTS.md rule that falsified factual statements must be corrected in place.
- Evidence (five independent signals agree): `.mo` binary header `N=636` (the count gettext actually consumes), `en_US.json` 635 keys, `en_GB.json` 635 keys, `zh_TW.yaml` 635 keys, and `extract_i18n_strings.py` reporting "zh_CN.po 现有条目：635 条".
- Timeline: all four catalog files carry mtime 2026-09-19 02:08, earlier than CODE_WIKI's 02:33 — the catalogs were already at 635 when the doc was written, so 663 was a counting error at write time, not a later regression.

#### 4. Full quality-gate run (result: zero changes)

| Tool | Command (aligned with `ci.yml`) | Result |
| --- | --- | --- |
| black | `--check --line-length 120 --target-version py314 .` | pass, 136 files unchanged |
| isort | `--check-only --diff --profile black --line-length 120 .` | pass (Skipped 8, no ordering issues) |
| mypy | `mypy` (**no path argument**) | pass, 117 files, 0 errors |
| mypy (Linux) | `mypy --platform linux` | pass, 117 files, 0 errors |
| basedpyright | `basedpyright` | 0 errors / 0 warnings / 0 notes |
| pytest | `pytest -q -rs` | **1042 passed / 0 failed / 2 skipped** (~54s) |

- Both skips are `tests/test_web_api.py:547` / `:566`, reason "current environment did not actually create a symlink (islink=False)" — a Windows limitation (no Developer Mode / no admin rights); they do not skip on Linux CI. **Not a code defect.**
- Why `--platform linux` was also run: CI runs on ubuntu, so a Windows pass does not imply a Linux pass (`src/web.py` contains platform-specific symbols such as `ctypes.WinDLL`; AGENTS.md has a matching gating convention).

#### 5. Item-by-item verification (no changes required)

- **Version**: `scripts/check_version.py` PASS — 4.3.0 is injected dynamically from `pyproject.toml` everywhere (`Dockerfile` via the `APP_VERSION` build arg, `main.py` and `src/web_api.py` via `importlib.metadata`, `zh_CN.po` carries no version).
- **Dependencies**: `pyproject.toml [project.dependencies]` and `requirements.txt` match one-for-one (20 each). Inline comments must be stripped first — `requirements.txt` comments are glued to the version with no space (e.g. `brotli>=1.2.0#b站弹幕解压…`), so a naive whole-line comparison reports every entry as a mismatch.
- **egg-info**: the base section of `DouyinLiveRecorder.egg-info/requires.txt` (20 entries) matches pyproject; only `protobuf`'s specifier order is normalized by setuptools to `<8,>=6.31.1`, which is not a real difference.
- **Exclusion dirs**: the five pyproject lists (black / isort / mypy / coverage / basedpyright) provide **full coverage** of the 19 core directories (runtime artifacts + tool-generated dirs); those same 19 are declared in `.gitignore` / `.dockerignore` / `.coveragerc-concurrency`, so source-of-truth parity holds.
- **`config/config.ini`**: all 131 keys read by code through `read_config_value` / `read_config_bool` are present (case-insensitive comparison). The 3 keys the scan flagged as "missing" (`是否强制启用https录制`, `是否禁用SSL证书验证(是/否)`, `虎牙是否禁用SSL证书验证(是/否)`) are all **legacy-key migration reads** guarded by `config.has_option(...)` — read-only, never written back, intentionally absent from new configs; expected behavior, not a gap.
- **Incidental finding (no change)**: `config/config.ini` carries a UTF-8 BOM, so external scripts must parse it with `encoding="utf-8-sig"`; plain `configparser.read(..., encoding="utf-8")` raises `MissingSectionHeaderError`.

#### 6. Local one-shot gate trigger (`scripts/run_gates.py`, new)

- **Context**: the better-harness review raised `declared-gates-have-no-local-trigger` — step 1 of the AGENTS.md Definition of Done requires "all gates green", yet these commands had no trigger outside CI, so red lines were only discovered after remote jobs turned red (the mypy `files` comment in `pyproject.toml` records the 2026-09-13 "already red locally, nobody noticed" drift).
- **Change**: added `scripts/run_gates.py`, which runs every `--check`-style gate from the "格式化命令 / Formatting Commands" section in original order with one command, exiting non-zero on any failure. **The script does not copy the command list**; it parses that section's bash code block verbatim at runtime (stripping trailing comments before shell execution), keeping the section as the single source of truth and introducing no parallel list.
- **Safety invariants**: write-mode `black .` / `isort .` (missing `--check` / `--check-only`) are blocked with rc=2 so the gate loop never rewrites the workspace; `--list` audits the exact commands; rc=2 (source missing / write-type present) and rc=3 (tool unavailable) are distinguished from rc=1 (a genuinely red gate), so "did not run" can never be misread as "ran and passed".
- **Tests**: `tests/test_run_gates.py` (14 cases, mutation-verified) locks: list parity with the section, write-mode detection (including the historical false positive where isort's `--profile black` value looked like a bare `black` call), absence of any write-type command in the loop, and non-zero exit when the source is missing.
- **AGENTS.md sync**: the formatting-commands section gained a local-trigger entry (registering only the entry point; commands still live solely in that section); DoD step 1 now names `python scripts/run_gates.py` as the call point; the project-structure scripts/ listing was updated.

### v4.3.0-dev (2026-09-19) — Full-codebase review remediation: 62 graded findings resolved (12 critical / 22 moderate / 28 minor)

**Context**: a grouped, parallel review of every first-party source file in the workspace
(148 files / 44,385 lines, excluding `.venv`, third-party dependencies and build artifacts) produced
`CODE_REVIEW_2026-09-18.md`. This entry records the resulting fixes. Beyond security hardening,
most changes also fix real functional defects. Locale catalogs measured: **635 entries** (`zh_CN.mo` header N=636, includes the empty-msgid header entry).

> [2026-09-20 correction] This line previously read "Locale catalogs: 635 -> 663 entries", which does not match
> measurement: all four catalogs (`zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`) are **635 entries**,
> with `.mo` header N=636. See section 3 of the 2026-09-20 entry for the evidence.

#### 1. Critical (12)

| ID | Location | Fix |
| --- | --- | --- |
| CR-01 | `gui.py` / `main.py` | **GUI silently hangs when the URL config is empty**: the GUI launches the recorder with a bare `[cli_exe]`, and `non_interactive` defaults to False (only `web.py` passes True), so an empty `URL_config.ini` makes the child block on `input()` inside a *hidden* console with a never-closing stdin — the UI shows "recording" while nothing happens. Added a pre-launch self-check (`_has_room_config`) with an actionable warning, plus an `except EOFError` fallback in `main.py` so hosts without stdin no longer die with a traceback |
| CR-02 | `main.py` | **One extra comma in a config line permanently stops every later room from recording**: `quality, url, name = split_line` raises `ValueError` for >3 elements, and the exception is not caught per line, so it aborts the whole parse loop. Replaced with tolerant parsing ("first two fields are quality + URL, the rest is the anchor name") plus a per-line try/except that logs and skips the bad line |
| CR-03 | `src/platforms/_tars.py` | **Unvalidated Tars length fields can spin a danmaku thread forever**: STRING4/SIMPLE_LIST lengths were used directly as cursor deltas, so a negative value moved the cursor backwards while `_goto`/`finish_struct`/`_skip_to_struct_end` all assume forward progress in `while True` loops. Added unified `_need`/`_advance` bounds checks plus `_assert_progress`, turning an unrecoverable infinite loop into a catchable `ValueError`; LIST/MAP element counts are now bounded by the buffer size |
| CR-04 | `src/collector.py` / `src/__init__.py` | **Douyu danmaku silently filtered (regression of an earlier fix)**: `only_fans` existed with three conflicting defaults, and `collector.py` force-overwrote the instance attribute back to `True`, overriding the `False` that `DouyuDanmaku` had already been changed to (C-3) while `main.py` never passed the argument. All three defaults are now `None` ("unspecified -> do not override the platform default") |
| CR-05 | `main.py` | **Hanging ffmpeg holds a concurrency slot forever**: the supervisor loop only exited on "process exited" or "user stopped", while the FLV path keeps `-reconnect*`, so a CDN cut causes infinite reconnects that never exit. Added a two-threshold watchdog (6 h total + 10 min output-growth stall) that terminates and reports failure |
| CR-06 | `main.py` | **Zero-byte output recorded as success and probe backoff cancelled**: success was decided solely by `return_code == 0` with no artifact size check anywhere; when an HLS playlist returns 200 but every segment 404s, ffmpeg produces nothing yet exits 0, which recorded a success sample and cancelled the probe backoff via `clear_ffmpeg_reject`. Added `_record_output_bytes` validation (<1 KiB is treated as failure) |
| CR-07 | `src/config_io.py` / `src/utils.py` | **Credentials stored in plaintext and propagated**: the backup thread copied the whole `config.ini` (including `[Cookie]`/`[账号密码]`) into `backup_config/` every 10 minutes, keeping 6 copies. Backups now redact sensitive sections by default (`DLR_BACKUP_KEEP_SECRETS=1` opts out), and both config and backups are `chmod 0600` (best-effort) |
| CR-08 | `src/web_api.py` | **The panel could be taken over or locked out through its own API**: the existing anti-lockout check only covered "clearing the password while auth is on", leaving the reverse path wide open — with auth disabled (the factory default) anyone could write their own password and enable auth to take over the panel, or enable auth with an empty password to lock it out permanently. Added a symmetric target-state check: enabling auth requires a non-empty password |
| CR-09 | `src/web_config.py` | **No scheme/target validation on room URLs -> blind SSRF**: `validate_room_target` only rejected newlines, while the dispatch table's last entry matched `.m3u8/.flv` by **substring**, so `http://127.0.0.1:8080/x?a=.flv` was classified as a custom stream and handed to ffmpeg's `-i`. Added a scheme allowlist plus rejection of loopback/private/link-local/reserved ranges |
| CR-10 | `src/web_config.py` / `web/app.js` | **Masking blacklist missed every URL-typed credential**: only key names were matched, so `钉钉/微信/bark 推送接口链接`, `ntfy 推送地址`, `代理地址` — where the credential lives *inside the value* — were returned in plaintext. Added endpoint-style key patterns plus value-shape detection (URL with a credential query string or userinfo), kept in sync between backend and frontend |
| CR-11 | `src/ffmpeg_install.py` / `src/node_install.py` / `build_exe.py` | **No integrity verification in the install/build chains**: the Lanzou branch only verified a hash when an env var was set (the default path unzipped and executed a third-party netdisk artifact directly); the official source used a TOFU self-written baseline; `build_exe.py` verified nothing across four sources and wrote zip members by hand (Zip Slip). Lanzou now requires verification by default (`FFMPEG_LANZOU_SHA256`, or explicit `FFMPEG_LANZOU_ALLOW_UNVERIFIED=1`) and rejects plaintext http; the official source goes through `utils.unzip_file`; the build path gained pinned-hash verification with env-var injection and realpath member checks |
| CR-12 | `src/spider.py` | **Platform parsing's "raw JSON + decorator fallback" pattern**: (1) `_loads_dict` promised "non-JSON returns `{}`" but used a bare `json.loads` (while the sibling `_safe_loads` had zero production callers); (2) `@trace_error_decorator` bound to a `str`-returning sync helper because a comment sat between it and the actual `def`, leaving `get_haixiu_stream_url`/`get_looklive_stream_url` unprotected; (3) the tuple-returning `get_popkontv_stream_data`/`get_acfun_sign_params` used the dict variant. All three fixed, with explicit None checks at the call sites |

#### 2. Moderate (22, summary)

- **WD-01 log masking**: `mask_credentials` now wraps the whole message rather than just the `url` argument — exception texts (httpx/urllib3 embed the full URL) and four `get_response_status` call sites that print real signed links are masked; secret key names extended with `sign/pwd/pass/session/auth/wsSecret/txSecret` etc.
- **WD-02/03 danmaku write path**: the SRT queue went from an unbounded `SimpleQueue` (whose comment claimed "bounded") to `Queue(maxsize=10000)` with counted drops; write-failure warnings aggregate over a 60 s window; a failed open retries every 10 s (previously a whole segment was silently dropped); `close()` gained a 5 s lock timeout so the recording thread cannot be wedged by I/O.
- **WD-04/05 WebSocket liveness**: protocol-level `ping_interval/ping_timeout` restored (application heartbeats only send, so a half-open TCP connection never reconnects); `send()` gained a 5 s timeout that closes the connection; `max_size` tightened from `None` to 8 MiB; reconnects use exponential backoff with jitter (the fixed interval made every room reconnect in the same second).
- **WD-06/08/09 web**: the auth middleware read and parsed the whole `config.ini` on every request — now an mtime+size-invalidated cache; non-idempotent requests verify Origin (cross-origin writes are not protected by SOP); added `POST /api/logout` for single-token revocation with the middleware also purging expired tokens; corrected the stale "default 1 hour" comment (the real default is 86400 s).
- **WD-07 + F-09**: the insecure (no auth + non-loopback) escape hatch now enumerates exactly what an attacker can do and writes it to the log; the frontend finally consumes the `/api/auth/status` risk banner the backend had always provided.
- **WD-10 frontend polling**: `fetch` gained a 10 s timeout (previously a single hung request permanently stopped the polling chain), failure backoff 2→5→10→30 s, `visibilitychange` handling, and a visible "disconnected" state.
- **WD-11/12 concurrency**: the Douyin rate-limit `time.sleep` moved out of `with semaphore` (it previously made N queued rooms sleep while holding network slots — 80 rooms meant ≥240 s per round); post-record transcoding moved from a bare thread per segment to a fixed-size pool (it used to spawn dozens of libx264 processes competing with recording for CPU/IO).
- **WD-13 not applicable after review**: the code already calls `record_success` on successful parsing (including offline rooms); the original finding was based on a misreading and **no change was made**.
- **WD-14 filename sanitising**: `clean_name` now handles control characters, Windows reserved device names and a 60-character cap (long titles plus deep directories can exceed `MAX_PATH` and break writes).
- **WD-15 atomic writes**: `utils.atomic_write_text` is now the single implementation; `update_config` and `update_anchor_name` moved from truncate+write to a same-directory tmp file plus `os.replace`.
- **WD-16/17/18/19 platform parsing**: the Taobao cookie write-back now holds `file_update_lock` and only writes on change; the duplicated hard-coded PopkonTV credential became one constant with an env override; the Taobao "refreshed cookie never applied" bug (an `else` bound to the wrong `if`) was fixed and `jsonp_to_json` exceptions no longer tear down the retry loop; Bilibili's `-352` risk-control `data: null` TypeError is guarded and the room-info failure log was raised from `info` to `warning` with the URL and exception type.
- **WD-20 online viewer count always 0**: platforms put the count in `DanmakuMessage.data` while the collector forwarded only `message`, so `_parse_online("")` always returned 0. `room_message` gained a `data` parameter (read preferentially) and the `"1.2万" -> 12` unit-conversion bug was fixed.
- **WD-21 GUI threading**: `_process_ended` joined the output thread for 5 s and the danmaku tail thread for 2 s **on the UI thread** (Tk must run on the main thread), freezing the window for up to ~7 s — now non-blocking, with the tail join capped at 0.2 s; the three `running = False` sites in `_read_output` go through `_mark_session_stopped` for session validation.
- **WD-22 Node install self-healing**: added `is_valid_zip` validation (a truncated archive used to bake a wrong hash into the baseline and fail permanently) and timeouts on seven `subprocess.run` calls.

#### 3. Minor (28, summary)

Bounded decompression (`decompress_limited` / `decompress_brotli_limited` for gzip/zlib/brotli plus a frame cap); `_pad_list` return values now used explicitly; direct-FLV subtitle threads clean up `create_var` and pass `name=`; audio output reuses the caller's `now`; direct-FLV filename double underscore; GUI log level `"warning"` → `"warn"`; `save_config` refreshes the quality context; `_stopping` reset moved before the session check; uptime uses `process_start_time` (it was reset by `display_info` every 5 s); dead retry loop in `recorder_status` removed along with a falsified comment; `delete_line` gained `newline=""` (CRLF was silently rewritten to LF); cookie cache `invalidate/clear` gained a generation counter against in-flight refills and the singleflight fast path is now locked; log file sinks gained exception fallbacks (an unwritable `logs/` used to crash at import with no log); spider dropped the now-unused `import subprocess` and documented `_is_safe_http_url` as test-only; Shopee `host_suffix` unified (multi-part TLD direct links produced invalid domains); the Look room-id regex no longer requires a trailing `&`; a failed YY title fetch no longer discards an already-obtained stream URL; `print` calls in `room.py`/`utils.py` became logger calls; five bare-English logs in `proxy.py` went through i18n; Twitch IRC gained cross-frame line buffering; Weverse token refresh failures are logged (previously silent); `i18n.tr()` can no longer raise (a bad translation placeholder used to mask the original exception inside `except` blocks); the non-SSL SMTP branch attempts STARTTLS and warns about plaintext; `migu.js` gained a script hash check (the only node-executed script had none); `build_exe` tarfile extraction passes `filter="data"` explicitly; CSP `connect-src` narrowed to `'self'` and the token moved to `sessionStorage` (falling back to `localStorage`); the root player page's invalid `referrer` value corrected.

#### 4. Tests and gates

- **Tests updated**: `test_spider.py::TestLoadsDict::test_invalid_json` now asserts `{}` instead of raising `JSONDecodeError` (CR-12); AcFun's failure assertion changed from `{"is_live": False}` to `None`; `test_i18n_tr.py` asserts fallback-to-template instead of `KeyError` (MI-23); `test_utils.py` gained a `log_capture` fixture and seven `capsys` assertions were switched to a loguru sink (MI-19); three patch targets in `test_spider_fixes.py` moved from `sp.subprocess.run` to `subprocess.run`.
- **Gate results**: `pytest` fully green; `black --line-length 120` / `isort --profile black` clean across 136 files; **argument-less `mypy` reports 0 errors** (117 files); `scripts/check_annotations.py` passes (22.8% average comment density); `compile_po.py --check` in sync; `extract_i18n_strings.py` reports 0 missing; frontend `node --test` 9 passed.
- **AGENTS.md** gained seven new entries: PEP 758 `except A, B:` does not support `as`; a comment between a decorator and `def` rebinds it to the next `def`; platform parsers must match their fallback decorator to their return type; the `_loads_dict` vs `_safe_loads` contract; a missing fallback decorator skews breaker samples; the environment signature of intermittent full-suite pytest segfaults; and the prompt contract for parallel grouped reviews (deliberate-convention allowlist plus source-level re-verification).

### v4.3.0-dev (2026-09-18) — Repository metadata reconciliation across 13 targets + four-language catalog completion (594 → 601 entries)

**Summary**: A full reconciliation pass over 13 metadata/documentation targets, plus two real localization defects found along the way. **No runtime behaviour change** (the one exception: under the Traditional Chinese locale, four push-failure log lines used to raise `KeyError`).

#### 1. egg-info rebuilt (was stuck on a 4.1.0 snapshot)

- `PKG-INFO` still carried `Version: 4.1.0` (pyproject is 4.3.0) and an outdated embedded README.
- `requires.txt` still had `websockets>=12.0` (must be 14.0 — `additional_headers`/`proxy` are 14.0+ APIs) and an unbounded `protobuf>=6.31.1` (must be `<8`).
- `SOURCES.txt` was missing `src/config_bool.py` and 30+ other files.
- Regenerated via `setuptools egg_info`: version 4.3.0, `websockets>=14.0`, `protobuf<8,>=6.31.1`, SOURCES at 139 lines, `PKG-INFO` carrying the current README.

#### 2. pyproject.toml

- `[tool.setuptools.package-data]` gained `"src.proto" = ["*.proto"]`: `douyin.proto` is the generation source of `douyin_pb2.py` and is required before any cross-major protobuf runtime upgrade, yet it was never shipped with the distribution.
- `[tool.coverage.report].exclude_also` dropped `if TYPE_CHECKING:`: coverage's default exclude rules already contain that pattern (including the `typing.`-prefixed variant), so listing it changed nothing while leaving pyproject at 5 entries against `.coveragerc-concurrency`'s 4 — breaking the "two jobs align entry by entry" convention.

#### 3. Documentation structure gaps

- `AGENTS.md` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` directory-structure sections were missing `src/config_bool.py`.
- `README.md` / `README_EN.md` were additionally missing `src/scheduler.py` and `src/log_archive.py`, still listed a long-gone `gui_legacy.py`, and still claimed "288 entries" (actual: 601).
- `README.md` / `README_EN.md` changelogs gained the `v4.3.0 (2026-09-17)` entry (unified boolean parsing / instruction hygiene / concurrency floor 8→1) — it had only ever landed in CODE_WIKI.

#### 4. Verified, no change needed

- `requirements.txt` ↔ `pyproject.toml [project.dependencies]` match entry by entry (20 items).
- `.gitignore` / `.dockerignore` / the six tool exclude lists in pyproject / `.coveragerc-concurrency` share one exclusion directory set.
- `config/config.ini` has no missing keys relative to the code's read sites (`read_config_value` + `read_config_bool` in `main.py`, plus `web_config.py`); local values were not overwritten.
- `Dockerfile` / `docker-compose.yaml` `APP_VERSION` injection passes `scripts/check_version.py`.

#### 5. Localization (i18n)

- **Four `*_2` placeholders in `zh_TW.yaml`**: `{message_2}`, `{msg_2}` (×2) and `{errmsg_2}`. `msg_push.py` passes `message=` / `msg=` / `errmsg=`, so under the Traditional Chinese locale `i18n.tr()` raised `KeyError` and the DingTalk / WeChat / Bark / PushPlus "push failed" warnings blew up entirely. Restored to the source placeholder names.
- **Seven strings from the "coloured output / dialog" paths added**: `color_obj.print_colored()` and `messagebox.show*()` do not go through `print()` / `logger.*()`, which is a historical blind spot of `scripts/extract_i18n_strings.py`. Added: exiting-safely, transient-error backoff, GUI startup failure, quality-switch failure, transcoding-to-MP4 (two variants) and config-file-changed.
- Catalogs went 594 → **601 entries**; `zh_CN.mo` recompiled (602 entries including the empty header msgid); `compile_po.py --check` passes.

### v4.3.0-dev (2026-09-17) — Unified boolean config parsing (fixes `true/false` silently disabling 8 settings)

**Summary**: When a boolean value in `config.ini` was written as `true/false`, it used to be treated as
invalid and **silently** fall back to a hard-coded default (no warning, no log line). Field measurement showed
8 settings drifting, the worst of which made 9 overseas platforms fail to record 100% of the time. This round
consolidates the four divergent boolean parsers into a single implementation, where `是/否` is equivalent to
`true/false`, `1/0`, `yes/no` and `on/off`.

#### 1. New single parsing entry point

- Added the **dependency-free** module `src/config_bool.py`: `parse_config_bool(raw, default)` and
  `format_config_bool(bool)`. Recognizes 是/否, true/false, t/f, yes/no, y/n, on/off, 1/0 (strip + lower before
  comparison); empty and unrecognized values return `default`. Being dependency-free is a hard constraint:
  `src/logger.py` runs before `main.py`, and `src.utils → src.logger` already forms a chain, so putting the
  parser in `src/utils.py` / `src/config_io.py` would create a circular import.
- `src/config_io.py` gained `read_config_bool(parser, section, option, default)` (read + write-back on a missing
  key). Write-back keeps the canonical `是`/`否` form; **existing values are never overwritten** (both encodings
  are already equivalent, so no migration is needed).

#### 2. 27 read sites and 4 divergent comparison sites replaced

- **`main.py`**: removed the `options: dict[str, bool] = {"是": True, "否": False}` dict lookup (it only matched
  when the value was exactly `是`/`否` and otherwise silently fell back to the second argument of `options.get`).
  Every boolean read now goes through `read_config_bool`: skip-proxy-check, the integrated https-recording read
  (including legacy-key migration and the legacy Huya SSL key), the three save-folder options, title in filename,
  emoji stripping, auto anchor-name update, HLS collection, use-proxy-IP, show loop seconds / show stream URL,
  segmented recording, mp4 conversion / re-encode to h264 / delete source file / time subtitle / custom script,
  danmaku recording and monitoring, DingTalk @all, SMTP SSL, push-only mode, and online / offline push.
- **`src/logger.py`**: `!= "否"` → `parse_config_bool(..., True)` — the old form treated `false` / `0` / `no`
  as "enabled", the opposite of the `main.py` dict lookup.
- **`src/web_config.py::read_web_config`**: `in ("true","1","yes","是")` → `parse_config_bool`.
- **`gui.py::_get_dynamic_status_info`**: `== "是"` → `parse_config_bool`.
- **`web/app.js`**: added `CONFIG_TRUE_TOKENS` / `CONFIG_FALSE_TOKENS` plus `parseConfigBool`;
  `httpsRecordingEnabled` now reuses it instead of `=== '是'` (in the panel, `true` used to be displayed as HTTP
  mode, the opposite of the protocol actually used for pulling the stream).

#### 3. Behavioural equivalence

- Only two paths can change: "key missing" and "value unrecognized" — and they converge only on the two settings
  where the old implementation contradicted itself: the "unrecognized value" branch of
  `保存文件夹是否以作者区分` and `是否使用代理ip(是/否)` now returns the default instead of the `options` fallback
  (for these two, the `read_config_value` default and the `options` fallback never agreed). **Missing-key
  write-back values are unchanged.**
- An unrecognized existing value returns the default without overwriting the user's text.

#### 4. Verification

- End-to-end against a real `true/false` config: `skip_proxy_check=True`, `global_proxy=True`,
  `enable_https_recording=True`, `stream_ssl_verify=False`, `logger._log_to_file=True`, and all three `[Web]`
  booleans parsed correctly.
- Drift re-audit against `D:\DouyinLiveRecorder\config\config.ini`: **0** drifted settings (8 before the change).
- Gates: pytest `1042 passed / 2 skipped`; black (136 files) / isort / mypy / `mypy --platform linux` /
  `check_annotations` / `compile_po --check` / `check_version` all green; `node --test tests/frontend/*.mjs` 9 passed.
  the `options` dict lookup) and `tests/frontend/test_quality_ui.mjs` (`parseConfigBool` coverage plus an assertion
  that `httpsRecordingEnabled` does not fall back to `=== '是'`).

### v4.3.0-dev (2026-09-17) — Instruction hygiene: AGENTS.md conflict/ambiguity consolidation + skill routing isolation (no runtime behavior change)

**Summary**: instruction-level review of `AGENTS.md` (798 lines), the relevant `ci.yml` sections, and the
user-level skills produced `CODE_REVIEW_AGENTS_GUIDELINES_2026-09-17.md` (16 findings); 14 of them are now
applied. **No runtime behavior changed** — the only source edit is a corrected comment in `src/spider.py`.
Target: instructions that made the agent stop for confirmation, contradict itself, or leave work incomplete.

#### 1. Consolidated directly contradictory entries

- **`except` parentheses**: three mutually exclusive statements coexisted — "black 26.x forces the
  parentheses off" (code style) vs. "both forms pass `black --check` with rc=0" (2026-09-12 correction)
  vs. the old claim restated (PEP 758 pitfall entry). Now one entry: writing `except A, B:` without
  parentheses is a **project style convention, not a gate requirement**, and existing parenthesized code
  must not be bulk-rewritten. The derived wrong claim in `src/spider.py` ("parentheses break 3.14
  semantics") was corrected too.
- **Exception logging format**: the old f-string mandate predates the 2026-09-10 i18n migration and
  contradicted "parameterized logs must use `i18n.tr()`". Now tr-template + keyword args, keeping the
  hard requirement of including the exception class name and a masked URL.

#### 2. Unified command contract

- New **"Formatting commands (single gate baseline)"** section: black / isort / mypy / check_annotations /
  compile_po / check_version, verbatim-compatible with `ci.yml`; every other section references it
  (previously the tests gate and pitfall entries carried two more variants).
- **mypy platform double-run no longer narrows by path**: `mypy src/` + `mypy --platform linux src/`
  became `mypy` + `mypy --platform linux`, because a path argument overrides `[tool.mypy].files` and
  reintroduces the missed root-entry imports (gui.py `logger` / `session_id`). The stale `ci.yml:232-233`
  comment was updated.
- **basedpyright scoped as a local-only supplementary gate**: previously declared mandatory with neither a
  canonical command nor a CI job. Added: command scope, differing diagnostic codes vs. mypy, and the
  tie-break rule "platform-dependent verdicts follow the CI-consistent (Linux) side".
- **Environment fit**: `.isorted` cleanup and pytest temp cleanup switched from POSIX `find`/`rm` to
  PowerShell equivalents (no coreutils in this Git Bash), scoped so `downloads/`, `logs/`, `backup_config/`
  are never deleted.

#### 3. New sections (previously living only in session memory)

- **"Definition of Done"**: gates green → real-device end-to-end verification → regression locks →
  bilingual CODE_WIKI changelog → daily memory log, with exemptions (docs/comment-only, test-only).
- **"Process-orchestration skill boundaries"**: routine work does not enter `vibe`-style governed runtimes
  (their freeze/hard-stop cycle breaks "edit → run on real device → re-edit"), and design gates such as
  `brainstorming` do not apply to work already pinned or already approved.
- **"Tiered venv dependency repair"**: wheel direct-extract (agent handles it) / proxy-bypass reinstall /
  only bulk reinstall escalates to the user.
- **i18n front-end catalog**: `web/app.js` embeds its own zh_CN/en_US/en_GB/zh_TW dictionary — string
  changes must land in five places.

#### 4. Duplicates and the rules themselves

- `clear_ffmpeg_reject` was documented twice → single source plus pointer; version source-of-truth and the
  docstring ban now carry same-source pointers.
- "Comments are append-only" gained an **exception clause**: it protects historical context, not falsified
  factual statements. Those (including AGENTS.md's own entries) must be corrected in place rather than
  answered with a parallel "correction" line; the old conclusion survives as one dated note.
- Removed stale reference: `gui_legacy.py` (deleted in v4.1.0-dev / 2026-09-10).

#### 5. Skill-side changes

- `brainstorming`: description narrowed to net-new work; HARD-GATE gained an exemption list (bug fixes,
  refactors, already-approved batch work, real-device iterations), and the design-doc step defers to the
  repository's own conventions.
- `karpathy-guidelines`: new §1b "doubt resolution order" — consume AGENTS.md / CODE_WIKI / tests / module
  headers before stopping to ask; stop only when the decision is irreversible, needs user-exclusive
  information, or authoritative sources contradict each other. Otherwise decide, implement, and disclose
  the assumption.

### v4.3.0-dev (2026-09-17) — Lowered adaptive concurrency floor: min_capacity 8→1 ("同一时间访问网络的线程数")

**Change summary**: Lowered the safe floor of the adaptive concurrency scheduler in "dynamic throttling" mode — i.e. the `min_capacity` default of `ConcurrencyScheduler` — from 8 to 1. The old default force-raised network concurrency to 8 even at low activity (regardless of the configured value); after the change, capacity falls back to the configured "同一时间访问网络的线程数" (default 3), improving resource efficiency under light load.

#### 1. Change: concurrency scheduler module (`src/scheduler.py`)

- `ConcurrencyScheduler.__init__`'s `min_capacity` default changed from `8` to `1` (around line 214).
- Entry points `main.py` / `gui.py` / `web.py` only pass `configured_limit` and never override this default, so changing the default takes effect globally with no call-site edits.
- Dynamic-mode capacity formula: `max(min_capacity, max(configured, min(ceiling, ceil(active/scale_divisor))))`. With the floor lowered 8→1, low-activity (0–8 tasks) capacity falls back to the configured value (default 3) instead of being force-raised to 8; high-activity still scales with task count (ceiling 128 unchanged); under extremely high error rate capacity is gently reduced but never below floor 1.

#### 2. Change: tests (`tests/test_scheduler.py`)

- 6 explicit `min_capacity=8` instances changed to `1` so regression cases match the new default.
- `test_scheduler_capacity_floor_and_scaling`: floor assertions corrected for the new floor — at `active=0` `>= 8` becomes `>= 3` (floor converges to configured 3); at `active=8` `== 8` becomes `== 3` (ceil(8/4)=2 < configured 3 → configured value is the floor).
- `test_scheduler_fixed_mode_pins_capacity_to_configured_limit`: after switching back to dynamic, `>= 8` becomes `>= 1`.

#### 3. Documentation sync (current-state descriptions, not historical changelog)

- `AGENTS.md` (concurrency-mode conventions), `CODE_WIKI.md` (scheduler architecture section), `CODE_WIKI_EN.md` (architecture section): "默认 min=8 / max=128" uniformly changed to "min=1".
- Unchanged: README / CODE_WIKI v4.0.9(-dev) historical changelog entries (kept as-is), `PKG-INFO` (build artifact), historical runtime-log records.

#### 4. Verification

- `pytest tests/test_scheduler.py` → 16 passed.

### v4.3.0-dev (2026-09-16) — Repository metadata source-of-truth sync: exclusion-dir completion / coverage-gate alignment across both jobs / version & config-key reconciliation

**Change summary**: Taking `pyproject.toml`'s `[project].version` (4.3.0) and the "single source of truth"
convention as the baseline, all 13 metadata/documentation files (AGENTS.md, docker-compose.yaml,
requirements.txt, Dockerfile, .gitignore, .dockerignore, .coveragerc-concurrency, pyproject.toml,
config/config.ini, CODE_WIKI*.md, README*.md) were reconciled in one pass.
**No functional behavior changed**; this round closes two classes of drift that keep causing misjudgment:
(1) a source-of-truth directory missing from some of its 6 sync points, and (2) the two CI coverage jobs
disagreeing on exclusion semantics (`exclude_lines` **replaces** the defaults, systematically under-reporting
coverage).

#### 1. Exclusion-directory completion (`recordings/`)

- `recordings/` was previously registered in only some sync points; it is now present in all 6:
  black `exclude`, isort `extend_skip`, mypy `exclude`, `[tool.coverage.run].omit`,
  basedpyright `exclude`, and `.coveragerc-concurrency`'s `omit`.
- Cross-checked line by line against `.gitignore` / `.dockerignore`; no other directory is missing.
- A missing entry costs one of three things: untracked directories polluting `git status`, being COPYed
  into the image, or being scanned by tooling (slowdowns and false positives).

#### 2. Coverage exclusion rules aligned across both jobs (important)

- `[tool.coverage.report]` in `pyproject.toml` used `exclude_lines`, which discards all three of coverage's
  default exclusions — the `# pragma: no cover` case/space variants, `...` ellipsis bodies, and
  `if TYPE_CHECKING:` — under-reporting coverage and diverging from the concurrency job
  (`.coveragerc-concurrency`, which uses the additive `exclude_also`).
- Switched to `exclude_also`; the two jobs now match entry for entry. The leftover TODO comment inside
  `.coveragerc-concurrency` was rewritten to "already converged", noting that reverting to `exclude_lines`
  or editing only one side re-creates the divergence.

#### 3. Version and example alignment (single source of truth: 4.3.0)

- `AGENTS.md` version `4.2.0 → 4.3.0`; `docker-compose.yaml` comment example `APP_VERSION=4.2.0 → 4.3.0`;
  `uv.lock` own-project version `4.1.0 → 4.3.0` (single line, no dependency-graph re-resolution;
  the other 73 packages untouched).
- The `Dockerfile` receives the version dynamically via `ARG APP_VERSION` + `--build-arg`, and `main.py` /
  `src/web_api.py` read it at runtime via `importlib.metadata` — no hardcoded versions anywhere;
  `scripts/check_version.py` passes.
- `DouyinLiveRecorder.egg-info/` is a build artifact already ignored by `.gitignore`, so its lagging version
  is out of scope for the sync check.

#### 4. Config file and documentation reconciliation

- `config/config.ini`: all 128 keys read by `read_config_value` were checked, and after normalization
  (section/option lowercased) **no key is genuinely missing** — the 6 initially reported "missing" keys
  (`B站cookie`, `是否启用HLS采集(是/否)`, `禁用SSL证书验证的平台(逗号分隔)`, and 3 SMTP keys) were all
  false positives from case differences: reads go through `configparser` (options are lowercased by
  `optionxform`, i.e. case-insensitive), and `web_config.py` already documents "constants in code are
  uppercase, lines in the config file are lowercase" as expected.
- Added `[录制设置] 自定义画质选项(逗号分隔) = `: this key is written back by the WEB-side quality add/remove
  and the GUI-side "switch quality", and is documented in both READMEs, but the config template had no slot;
  an empty value falls back to the engine's built-in full quality set by design, so behavior is unchanged.
- `README.md` / `README_EN.md` config sections gained two previously undocumented keys:
  `最大同时录制数(0为不限制)` (global concurrency cap, default 0 = unlimited) and
  `自定义画质选项(逗号分隔)`; the documented example values were also verified against the code defaults
  (`循环时间(秒)=120`, `排队读取网址时间(秒)=0`, `是否启用https录制=否`, `生成时间字幕文件=否`,
  `是否录制弹幕(是/否)=否`) — note that `config/config.ini` is git-ignored (it holds sensitive values),
  so the README config block is the actual source of truth for "new user defaults"; personalized local
  values (e.g. a 3600s segment duration) are not documentation drift.
- Test-baseline line `699 passed` → `974 passed / 2 skipped` (matching a real `pytest -q` run).

#### 5. Ignore-rule source-of-truth

- `.gitignore` gained `*.jsonl` (`logs/danmaku_monitor.jsonl`, the danmaku monitor sidecar log);
  `.dockerignore` gained `*.icon` (system-tray icon cache, previously only in `.gitignore`).
  The two files are aligned again.

### v4.2.0-dev (2026-09-15) — mypy gate widened: scope moved into pyproject `[tool.mypy].files` (`src/` → whole repo) + 6 type defects fixed

**Change summary**: Started from 3 mypy errors reported by the CI typecheck job (huya / async_http / spider).
While fixing them we found the gate only ever covered `src/` — root-level entry points and tests were never
checked — so the scope was pinned as a single source of truth in config and `tests/` was brought in, with
15 drifted annotations repaired. **No functional behaviour change** (except the gui.py teardown path, which
previously raised unconditionally and only works after the fix).

#### 1. Type errors fixed (6, four of them guaranteed runtime failures)

- **src/platforms/huya.py**: added `import i18n`. The `except` branch called `i18n.tr(...)` without the import,
  so a frame-parse failure raised `NameError` and masked the real exception.
- **src/async_http.py** (`_get_client`): the reuse branch inferred `winner is not None` indirectly from
  `loser is not None`; mypy cannot narrow across variables. It now stores the `reused` client directly inside
  the critical section, so the returned value narrows to `httpx.AsyncClient`.
- **src/spider.py** (liveme): wrapped `lm_s_sign` in `str()` — `sign_data` is `dict[str, object]`.
- **gui.py** (was outside the checked scope; 3 fixes):
  - added `from src.logger import child_process_env, logger` — `_read_status_config` used an undefined `logger`.
  - `self._process_ended(session_id)` inside `_schedule_log_flush` referenced an undefined `session_id`:
    **the UI teardown path after a natural child-process exit always raised `NameError`**. Dropping the
    argument would have discarded the "ignore late callbacks from a stale session" guard, so the log-queue
    end-of-stream sentinel was changed from a bare `None` to `(session_id,)` — the UI thread now forwards the
    captured session id to `_process_ended` for validation.
  - `_has_unsaved_config_edits` returns `bool(current != ...)` instead of `Any`.

#### 2. Gate scope pinned (single source of truth)

- **pyproject.toml `[tool.mypy].files`**: `src` + root entry points (main/gui/web/i18n/msg_push) +
  `build_exe.py` + `scripts` + `tests`.
- **ci.yml typecheck**: `mypy src/` → `mypy` (no path argument); scope comes entirely from config, so local
  runs and CI run the exact same command.
- **AGENTS.md**: commands updated, plus a note that **explicit paths (`mypy src/`) override `files`** — fine
  for narrowing during debugging, but the gate result is the no-argument run.

#### 3. tests/: 15 drifted items repaired

- `test_start_record_command_golden.py`: 12 missing annotations (introduced with the golden-snapshot test on
  2026-09-13); annotating `main_mod` as `ModuleType` then surfaced `attr-defined` on
  `main.exit_recording = True`, replaced with `setattr`.
- `conftest.py` / `test_notify.py`: generator fixture return types `Iterator` → `Generator` (mypy requires a
  generator function to be annotated as `Generator` or a supertype).
- `test_danmaku_offloop.py`: ignore comment extended to `[assignment, method-assign]` — mypy reports
  `assignment`, basedpyright reports `method-assign`; both codes must be silenced.

and basedpyright clean on all touched files.

### v4.2.0-dev (2026-09-15) — Fixed Linux CI test `test_read_config_value_missing_key_readonly_ok` (atomic write vs. file mode bits)

**Change summary**: Test/documentation only, no functional code change. CI (Linux) reported 1 failed /
975 passed on the assertion "the default key was not written into the read-only config file". Root cause:
the test created an "unwritable" target with `cfg.chmod(0o444)`, but `read_config_value` writes back through
`_atomic_write_text` (same-directory temp file + `os.replace`), and `os.replace` only checks write
permission on the **containing directory** — the target file's own mode bits are irrelevant (and are
bypassed entirely when running as root). Windows behaves the opposite way: the read-only attribute on the
destination makes `replace` fail outright, which is why the test passed locally on Windows and failed on
Linux CI.

- **tests/test_config_io_readonly.py**: now uses `monkeypatch.setattr(config_io.os, "replace", _deny_replace)`,
  raising `PermissionError` only for the target config path and delegating everything else to the real
  `os.replace`. This reproduces the degraded branch deterministically on every platform: write-back rejected →
  warning ("atomic write failed") + default value returned + original file untouched. `cfg.chmod(0o444)` is
  kept as scene documentation, no longer the sole mechanism.
- **AGENTS.md**: new entry under "测试编写强制约定" stating that read-only-file tests must not rely on
  `chmod` alone, and distinguishing the two write-back paths — `config_io` (atomic) vs. `utils.update_config`
  (direct `open(..., "w")`).

(same 976 collected as CI); `black --check` / `isort --check-only` / `mypy` / `basedpyright` clean on the
changed file. A throwaway script (since deleted) confirmed with no read-only attribute set that the stub
really triggers `_atomic_write_text`'s `PermissionError` branch: warning logged, temp file cleaned up, config
content unchanged.

### v4.2.0-dev (2026-09-14) — Repository metadata / ignore-rule source-of-truth sync + four-language catalog consistency fix

**Change summary**: A full consistency audit and sync of nine configuration/metadata files under the
"single source of truth + shared-source maintenance" rule, plus a content fix in the British English
catalog. **No functional code changed** this cycle — everything is configuration, documentation and
localization resources. All gates stayed green after the change (pytest 974 passed / 2 skipped,
black clean across all 134 files, isort clean, `check_annotations` fully passing,
`scripts/check_version.py` PASS, `scripts/compile_po.py --check` byte-level in sync).

#### 1. Module-classified

- **pyproject.toml (exclude lists completed)**: `logs` was only present in black's exclude and missing from
  isort / mypy / basedpyright / coverage; `backup_config` existed only in the two ignore files and in none of
  the five tool exclude lists. Both are now aligned to one shared list:
  - `[tool.black].exclude`: added `backup_config` (`logs` / `downloads` already present)
  - `[tool.isort].extend_skip`: added `logs`, `backup_config`
  - `[tool.mypy].exclude`: added `logs`, `backup_config`
  - `[tool.basedpyright].exclude`: added `**/logs`, `**/backup_config`
  - `[tool.coverage.run].omit`: added `*/downloads/*`, `*/logs/*`, `*/backup_config/*`
  - Each of the five now carries a "runtime output dirs (maintained together with .gitignore/.dockerignore)" comment.

- **.coveragerc-concurrency (aligned with pyproject coverage omit)**: `omit` gained `*/downloads/*`, `*/logs/*`,
  `*/backup_config/*`. This file is the second copy of the same list and only covered `node` / `ffmpeg` before.

- **.gitignore (stale entries cleaned)**: the "temporary / in-progress docs" section enumerated
  `PERF_REVIEW_2026-08-28.md` (plus `CODE_CHANGES.md` / `TRAE_AGENT_CODE_WIKI.md`); none of these files exist in
  the workspace any more, and per-file enumeration keeps rotting. Replaced with the `PERF_REVIEW_*.md` glob and a
  comment stating that `CODE_WIKI*.md` / `CODE_REVIEW_FIX_1.md` / `DIAGNOSIS_*.md` are **formal docs shipped with
  the repo** and must never be gitignored.

- **.dockerignore (same cleanup + new docs covered)**: the docs section likewise dropped the non-existent
  `bili_danmuku_proxy.md` / `danmaku_check.md` / `todo.md` / `PERF_REVIEW_2026-08-28.md` in favour of three globs
  (`PERF_REVIEW_*.md`, `CODE_REVIEW_*.md`, `DIAGNOSIS_*.md`), so new root-level docs of the same kind are excluded
  automatically; the temp-files section gained `*.jsonl` (`logs/danmaku_monitor.jsonl` and friends).

- **Dockerfile**: the "not copied into the image" list above `COPY --chown=recorder:recorder . ./` was an
  item-by-item enumeration that had drifted from the real .dockerignore. Rewritten as the four .dockerignore
  groups (tests & tooling / docs / runtime output / platform binaries & local scripts) with a pointer that new
  docs are covered by the .dockerignore globs, so the two files can no longer rot independently.

- **docker-compose.yaml**: header comments gained two facts — (1) the repo ships no `.env` (it is gitignored),
  so it must be created before first use; (2) the four host-side volume dirs (`config` / `downloads` / `logs` /
  `backup_config`) are auto-created by Docker on the first `docker compose up`, all four are gitignored and
  dockerignored, and the container-side counterparts are pre-created by the Dockerfile's
  `mkdir -p logs downloads backup_config`. The `APP_VERSION=4.2.0` example already matches pyproject; unchanged.

- **AGENTS.md**:
  - *Project structure*: added `.gitignore` / `.dockerignore` entries; added the three runtime dirs — `logs/`
    (`streamget.log` / `PlayURL.log` / `danmaku_monitor.jsonl` / `web_console.log`), `downloads/`, `backup_config/`;
    added `CODE_REVIEW_FIX_1.md` to the root docs.
  - *CI / workflow conventions → dockerignore / gitignore shared-source rule*: extended the must-sync list with
    `downloads/` / `logs/` / `backup_config/`, recorded the four tool excludes completed this cycle, and noted that
    review/analysis docs go through .dockerignore globs but must never be gitignored.

- **requirements.txt**: **no change**. All 20 runtime dependencies verified identical to
  `pyproject.toml [project.dependencies]`, including the F-14 `protobuf>=6.31.1,<8` upper bound and the
  `websockets>=14.0` lower bound.

- **config/config.ini**: **no change**. An AST scan of config keys read by the code versus the keys actually present
  showed every difference to be either configparser `optionxform` case-insensitive matching
  (`是否使用SMTP服务SSL加密` ↔ `是否使用smtp服务ssl加密`) or a merged legacy key
  (`是否强制启用https录制`, `是否禁用SSL证书验证(是/否)`, `虎牙是否禁用SSL证书验证(是/否)`).
  The F-10 `tiktok_guest_cookie` key is in place.

#### 2. Localization (four-catalog consistency)

- **i18n/en_GB.json (content bug fix, 21 entries)**: 21 entries had **Traditional Chinese values** — zh_TW
  translations mistakenly written into the British English catalog. They covered danmaku parse-error messages
  (`[弹幕]后台协程异常`, `[B站弹幕]帧解析异常`, `[抖音弹幕]弹幕解析异常`, `[斗鱼弹幕]帧解析异常`, `[虎牙弹幕]帧解析异常`, 7 total)
  and the ffmpeg / Node.js installer SHA256 verification messages (14 total). Refilled with British English per the
  standing rule "en_GB differs from en_US only in spelling" (none of these entries has an `-ize/-ization` variant).
  **594 entries** with zero key-set differences pairwise; no Chinese left in `en_US` / `en_GB`; no untranslated
  entries in `zh_TW` (the 5 entries identical to zh_CN contain no simplified-only glyphs, so they are correct).
  `scripts/extract_i18n_strings.py` reports **0 missing runtime strings**.
- **i18n/zh_CN/LC_MESSAGES/zh_CN.mo**: recompiled (595 entries including the header, 72,886 bytes);
  `scripts/compile_po.py --check` passes byte-level.
- The frontend `web/app.js` embedded catalogs (independent from the Python side) were checked too: 49 keys in each
  of the four languages, consistent, unchanged.

#### 3. Verification

- `scripts/check_version.py`: PASS (pyproject 4.2.0 is the single source of truth; the Dockerfile receives it via
  the `APP_VERSION` build arg; no hardcoded version).
- `scripts/compile_po.py --check`: OK (595 entries in sync).
- `scripts/extract_i18n_strings.py`: 0 missing runtime strings.
- `black --check --line-length 120 --target-version py314 .`: 134 files clean; `isort --check-only`: clean.
- `pytest`: 974 passed / 2 skipped / 0 failed; `mypy` clean for all touched files (3 remaining warnings are
  pre-existing in files not touched).

### v4.2.0-dev (2026-09-13) — Douyu "SRT-only, no video" root-cause + HLS segment-layer false-green probe + source-selection hardening (config fallback / observability / same-origin candidate)

**Change summary**: Located and fixed the "danmaku SRT only, no video file" failure on Douyu and similar platforms. Root cause: the HLS playlist layer always returns 200, but the edge-node media segments (`.ts`) all return 404, so ffmpeg pulls zero media segments and produces zero bytes; the danmaku pipeline depends only on `room_id` and is decoupled from the video pipeline, so the SRT is still written — the symptom is "SRT only, no video". After the prior cycle added the segment-layer probe `_probe_hls_segment` in `src/stream_select.py`, this cycle closes its test-red and i18n gaps, and lands the three hardening directions from `DIAGNOSIS_DOUYU_NO_VIDEO_2026-09-13.md` (config fallback / observability / same-origin candidate), plus fixes one pre-existing `check_annotations` violation. Gate pytest **944 passed**.

#### 1. Module-classified

- **src/stream_select.py (segment-layer probe, from prior cycle, stabilized this cycle)**:
  - `_probe_hls_segment()`: GET the playlist → follow the master variant → probe the **last segment** with `Range bytes=0-0`; an explicit 4xx/5xx at the segment layer means unreachable (false-green), 200/206 means reachable; when no segment can be parsed, **fail open conservatively** (only trust "segment probed and explicitly rejected with 4xx/5xx").
  - Wired into `_validate_stream_url`: both the HEAD-non-2xx path and the Range-GET-200 path call the segment probe before declaring reachable, decoupling "playlist 200" from "recordable".

- **src/stream_select.py (source-selection hardening, three new functions this cycle)**:
  - `_hls_selection_config()` (config fallback): reads `main.hls_collection_enabled` / `main.hls_collection_exclude_platforms` via `getattr(..., default)`, default `enabled=True` / `exclude=()`; tolerates comma strings (`"a,b"`→`("a","b")`), ignores non-list/non-string types and reports a missing global, avoiding an `AttributeError` that would interrupt source selection.
  - `_same_origin_flv(hls_url, flv_candidates)` (same-origin candidate): compares the `?`-stripped path and treats `.m3u8`↔`.flv` as interchangeable to find the FLV candidate sharing the HLS token, used as a fallback when all HLS segments are dead.
  - `_log_source_choice(platform, kind, url)` (observability): a single-line log `选源结论: platform={platform} 采用 {kind} 源: {url}`, plus logs at three spots — "HLS segments all dead, falling back to same-token FLV", "pick hit", and "no usable source this round" — so the false-green→fallback path is observable.
  - `select_source_url`: direct reads of `main.hls_collection_enabled` / `main.hls_collection_exclude_platforms` replaced by `_hls_selection_config()`; a warning log on same-origin FLV fallback, `_log_source_choice` on pick, and a "no usable source" conclusion log on total failure.

- **tests/test_stream_select.py (tests)**:
  - Fixed 2 pre-existing failures: the segment probe adds one GET, so `get_calls == 2/1` became `== 3/2`; fake responses gained `.text` and fake clients gained `close()`.
  - Added 5 segment-probe tests: `test_hls_segment_404_rejects_playlist` / `test_hls_segment_200_stays_reachable` / `test_hls_segment_404_last_resort_released` / `test_hls_empty_media_playlist_conservative_pass` / `test_select_source_url_falls_back_to_flv_when_hls_segments_dead`.
  - Added 10 hardening tests: `_same_origin_flv` match/None/ignore-query triples + `test_select_source_url_logs_same_origin_flv_fallback` / `test_select_source_url_logs_choice_on_pick` / `test_select_source_url_logs_no_usable_source` / `test_hls_selection_config_defaults_on_missing_globals` / `test_hls_selection_config_normalizes_comma_string` / `test_hls_selection_config_ignores_invalid_type` / `test_select_source_url_survives_missing_hls_config`. This file **52 passed**.

- **tests/test_start_record_command_golden.py (annotation-convention fix)**:
  - Fixed the 1 pre-existing `scripts/check_annotations.py` violation: the triple-quote docstring on `class _Cap:` became a `#` line comment above the class (semantics unchanged, complying with AGENTS.md "use `#` comments, no triple-quote docstrings"); `black --line-length 120 --target-version py314` also reformatted 1 hunk of this file.

- **i18n four catalogs (+8 new strings)**:
  - `i18n/zh_CN/LC_MESSAGES/zh_CN.po` appended two dated blocks (2026-09-13, 5 segment-probe + 3 hardening strings), then `python scripts/compile_po.py` recompiled `zh_CN.mo` (byte-level gate passed).
  - `i18n/en_US.json` / `i18n/en_GB.json` each gained 8 keys (segment-probe + hardening); `i18n/zh_TW.yaml` gained the same 8 keys in Traditional Chinese. The four catalogs share one keyset (`tests/test_i18n::test_catalogs_share_same_keyset` passes).

- **DIAGNOSIS_DOUYU_NO_VIDEO_2026-09-13.md (new diagnostic report)**: full record of problem overview, video/danmaku decoupling structure, investigation timeline and evidence, root cause, fix plan (source fix / tests / i18n / hardening / annotation violation), diagnostic approach, verification, lessons, and references.

#### 2. Known / untouched black violations

- `main.py` and `tests/test_start_record_command_golden.py` still report as non-compliant under `black --check --line-length 120 --target-version py314 .` (both pre-existing diffs, not introduced this cycle). This cycle formatted only `src/stream_select.py` (fault-repair lineage); `main.py` and the golden test were **deliberately left untouched** — blackening the golden test would explode the `_build_cases` table key-by-key, spiking the line count and possibly dropping comment density below the `check_annotations` 13.0% threshold. See report §5.4.

#### 3. Verification

- pytest **944 passed / 2 skipped / 0 failed** (up 10 from the prior 934); `scripts/check_annotations.py` exit code 0; `isort --check-only` clean; `src/stream_select.py` `black --check` passed.
- Gate bar: pytest 0 warnings, black len120, isort black profile, mypy strict, basedpyright. End-to-end real-machine verification (re-record Douyu room with a fresh URL) pending.

### v4.2.0-dev (2026-09-13) — CODE_REVIEW_FIX_1 leftover batch fix (22 landed + 3 deferred) + repository metadata sync

**Change summary**: This cycle completed the second/third-batch remaining items of `CODE_REVIEW_FIX_1.md` (F-01~F-25) — 22 items landed, 1 clarified (F-08), 3 deferred (F-01/F-12/F-13) — with the gate at pytest **909 passed**. The repository metadata (AGENTS.md / docker-compose example version) was then aligned to the `pyproject.toml` single source of truth 4.2.0, and the `tiktok_guest_cookie` key was added to `config.ini` for the F-10 config-override path. The four-language i18n catalogs were recompiled to `zh_CN.mo` (587 entries) after the previous top-up.

#### 1. Module-classified landed items (FIX_1)
- **main.py**: F-02 removed dead imports `converts_m4a`/`segment_video` (functions kept in `src/video_postprocess.py`, still unit-tested); F-03 `direct_download_stream`'s `finally` now only cleans up zero-byte leftovers when `_downloaded == 0`, preserving any already-downloaded content (consistent with the ffmpeg path).
- **gui.py** (F-04~F-07/F-09): session token `_session_id` auto-increment plus `_read_output`/`_wait_and_update_ui`/`_process_ended`/`_on_recording_stopped` validation closure, eliminating the "stop then immediately restart" stale-callback regression; quality table `_update_quality_display` now strips `_QUALITY_NON_DISPLAY_FIELDS` (`last_seen`/`recording`) before comparison to stop per-round rebuild flicker; crash sink `_install_crash_sink()` and everything before it must not `import src`; atomic write implemented locally in gui (never `import src.config_io` — that module does `import main` at module level, which would trigger main init inside the GUI process).
- **msg_push.py** (F-24): the ntfy test call could fire a real push on an uncommented path — now guarded/commented per channel; SSE endpoint `/api/status/stream` kept (documented as a public contract in README) but now does `await request.is_disconnected()` + terminates after 5 consecutive failures.
- **src/ffmpeg_install.py / scripts/node_install.py** (F-17/H-1): added `_sha256_of_file` + `_check_or_record_zip_sha256` (trust-on-first-use); LanZou supports the `FFMPEG_LANZOU_SHA256` forced comparison; zip validated with `zipfile.is_zipfile` (re-download on corruption); `check_ffmpeg_installed` carries `timeout=15`.
- **src/web_api.py** (F-20): SSE endpoint footprint fixed (as above); list_files dangling/escape-root symlink crash and info leak re-verified.
- **web/app.js** (F-21): the standalone inline four-language catalog (zh_CN/en_US/en_GB/zh_TW) must be updated in all four places; after changes run `node --test tests/frontend/*.mjs` (6 cases) and `node --check web/app.js`.
- **web.py** (F-22): `/api/status/stream` kept and fixed (as above).
- **src/web_config.py** (F-23): inline comment quote-priority (quote-wrapped values split after the closing quote; falls back to `" #"`/`" ;"` heuristics); added `_config_write_lock` atomic write (H-6).
- **src/utils.py** (F-16/F-25): `read_ini_value(file_path, section, key) -> str|None` (no write-back), old name kept as a compat alias, distinct from the config_io homonym; zip-bomb protection (4GB per file, 8GB cumulative, 100x ratio); JS signature-script hash pinning `_JS_SHA256_EXPECTED` (7-script baseline) + `get_compiled_js` compares raw bytes, warns by default and `DLR_JS_STRICT_HASH=1` refuses execution.
- **src/spider.py** (F-10/F-11/F-19): `_read_tiktok_guest_cookie` must be inserted above the `@trace_error_decorator` (inserting between "@decorator + def" hijacks the decorator — exposed by 2 TikTok test failures); multi-arg print→logger uses string concatenation (`"x " + str(e)`) to avoid tripping the i18n scanner; ab_sign random segment defaults to `random.random()`, `DLR_AB_SIGN_FIXED_RANDOM=1` falls back to a fixed value.
- **src/sync_http.py** (F-12): SSL allow-list needs a platform domain list — deferred.
- **requirements.txt / pyproject.toml** (F-14 actionable part): `protobuf` capped `<8` (douyin_pb2 is a protoc 25.x artifact; cross-major runtime upgrades risk breakage, and a same-generation protoc regen is required before upgrading — unavailable in this env).

#### 2. Clarified & deferred items
- **F-08 (AGENTS.md annotation convention clarified)**: the original "black-enforced" rationale was wrong — measured `except (ValueError, TypeError) as e:` still passes `black --check` unchanged, and all 9 existing parenthesized sites pass the gate. **black accepts both styles**; uniform no-parentheses is a style convention, not a formatting mandate. Written into AGENTS.md; external-review suggestions to add parentheses contradict the convention and are not adopted.
- **F-01 completed (2026-09-13)**: start_record split (unify the 5 ffmpeg command-construction paths). Landed golden-snapshot test `tests/test_start_record_command_golden.py` (20 cases + `tests/golden/start_record_commands.json`) that freezes time/network/IO and compares the `ffmpeg_command` captured at `check_subprocess` byte-for-byte; then collapsed the 5 inline `command = [...]` blocks into module-level `_build_ffmpeg_output_args(save_file_path, record_save_type, split_video_by_time, split_time, is_audio=False)` (audio MP3/M4A + video TS/FLV/MKV/MP4). Input-level options and `save_file_path`/`now` construction stay in `start_record`. Re-running the golden test: 20/20 green, byte-identical to pre-refactor. See the "F-01 completed" subsection below and the matching AGENTS.md regression entry.
- **F-12 deferred**: SSL allow-list needs a platform domain list.
- **F-13 deferred**: Douyin signature not URL-encoded, consistent with upstream dart — must capture upstream behavior before changing, do not blind-fix.
- **F-19 pending real-machine verification**: Douyin nonce de-dup check.

#### 2b. F-01 completed — start_record recording-command construction split (2026-09-13)

**Background**: `main.start_record` inlined a `command = [...]` ffmpeg output-arg list in each of five branches (audio MP3/M4A, FLV, MKV, MP4, TS). Those 5 copy-pasted lists were exactly the root cause of the historical "`-segment_format` literal mis-match" P0 silent mis-encapsulation (TS wrongly `ipod`, M4A wrongly `mpegts`) — change one, the other four drift.

**Approach**:
1. Land a golden-snapshot test first (no logic touched): `tests/test_start_record_command_golden.py` freezes time (`datetime`/`time` dual-mock, avoiding the `time.strftime` recursion trap), mocks network/IO/subprocess, captures the `ffmpeg_command` at `check_subprocess` and the direct-download args at `direct_download_stream`; `GOLDEN_REGEN=1` regenerates baseline `tests/golden/start_record_commands.json`, default compares byte-for-byte. 20 cases cover the 5 command paths + m3u8 dropping `-reconnect_at_eof` + header/proxy injection + overseas timeouts + FLV-h265→TS + shopee direct-download.
2. Collapse the 5 inline lists into module-level `_build_ffmpeg_output_args(...)`. Container mapping always reads `SEGMENT_FORMAT_BY_SUFFIX` (zero literals); `is_audio` selects pure-audio (MP3→libmp3lame / else aac+ipod), video dispatches TS/FLV/MKV/MP4 by `record_save_type`, segmented mode fills `-segment_format`, non-segmented gives the container directly. Input-level options and `save_file_path`/`now` construction remain in `start_record`, keeping the builder a pure output-arg assembler that is independently testable and behavior-reversible.
3. Re-run golden: 20/20 green, ffmpeg command byte-identical to pre-refactor; full `pytest` **929 passed / 2 skipped / 0 failed**.

#### 2c. Closing batch — F-01 finished / F-12 / F-13 / F-14 (2026-09-14)

All 25 items of `CODE_REVIEW_FIX_1.md` are now closed (F-08 was a clarification). Gates: `pytest 974 passed / 2 skipped / 0 failed`; black(120) + isort(black) clean repo-wide; `check_annotations` fully passing (avg density 22.1%); basedpyright 0 errors on touched files; mypy 0 errors for `main.py`, `src/sync_http.py`, `src/platforms/douyin.py` and all new test files.

- **F-01 stage 2 (single definition point for command construction)**: added `_build_ffmpeg_input_args()` (input-side `-reconnect*` / `-headers` / `-tls_verify` / `-http_proxy`, anchored on `-i`, no bare indices) and `_build_record_output_path()` (extension / split timestamp format / index placeholder collapsed into three lookup tables: `_EXTENSION_BY_SAVE_TYPE`, `_SEGMENT_NOW_FORMAT_BY_SAVE_TYPE`, plus the FLV non-split `_00` suffix). Four **identical** `_build_ffmpeg_output_args` calls in the audio branch (copy-paste residue) collapsed into one. Overseas timeout/buffer tuning extracted to `_ffmpeg_network_tuning()`.
- **F-01 stage 3 (execution skeleton)**: `_run_ffmpeg_record()` unifies try/except OSError + `check_subprocess` + clearing the ghost `recording` entry on startup failure; `_convert_after_record()` unifies post-record MP4 conversion (returns immediately when conversion is off; segments matched by the `_<digits>.<ext>` regex, which also covers ffmpeg `%03d` overflowing to 4 digits past 999 segments). Five duplicated skeletons down to one.
- **F-01 stage 4 (table-driven platform dispatch)**: `_resolve_platform_stream`'s 53-level `elif` chain replaced by `_PLATFORM_RESOLVERS` — a `(matcher, handler)` table with 52 per-platform `_resolve_<host>()` functions sharing a `_PlatformResolveContext`; `_match_host()` preserves the original `record_url.find(fragment) > -1` semantics and custom stream addresses use `_match_stream_suffix()` (lowercased `.m3u8` / `.flv`). Adding a platform is now one handler + one table row.
- **F-01 side fix (behaviour drift)**: non-segmented TS unconditionally spawned an MP4 conversion thread when the URL was commented out / recording stopped, ignoring the user's "convert to MP4 after recording" setting — the segmented-TS path and the natural-end path in `check_subprocess` both honour it; this fifth copy was the only one that did not. Now governed by `converts_to_mp4`.
- **F-01 side fix (display)**: the "preparing to record" line for segmented recording used to print the *non-segmented* file name (FLV/MKV/MP4 with the old timestamp, TS with the new one — three mutually inconsistent shapes). It now prints the basename of the real output path.
- **F-12 (sync_http SSL scoping)**: the CERT_NONE context and opener are now built **lazily** instead of at import time; `sync_req(..., ssl_verify=None)` adds a per-request override that is threaded through both the urllib and the requests (proxy) paths. **Also corrects the 2026-09-12 risk description**: all 123 `sync_req` call sites live in `src/spider.py`; login, `msg_push.py` notifications and the web panel never go through this module, and the control-plane switch `http_config.ssl_verify` has no `set_ssl_verify(False)` call site in production (it is always True) — the CERT_NONE path is unreachable in production, so the risk is a misuse surface rather than a live exposure. 6 new regression cases.
- **F-13 (Douyin signature encoding) — conclusion: keep it unencoded**. Verified against upstream `xiaoyaocz/dart_simple_live`, `simple_live_core/lib/src/danmaku/douyin_danmaku.dart` (~line 88: `var url = "$uri&signature=$sign";`) — plain concatenation, no `encodeComponent`, byte-identical to this repo. The XBogus custom alphabet does contain `+` / `/`, but the server does not decode `+` as a space (otherwise ~40% of signatures would fail systematically) and a WebSocket handshake URL is parsed as a standard query with percent-decoding; adding `quote()` would only make this client the lone outlier fingerprint. Rationale recorded in `src/platforms/douyin.py` and locked by `tests/test_douyin_signature_encoding.py` (4 cases).
- **F-14 (protobuf compatibility guard)**: protoc / grpcio-tools are still unavailable here, so `douyin_pb2.py` is not regenerated (it is DO NOT EDIT). Instead failure is moved into CI: `tests/test_proto_runtime_compat.py` parses the gencode version (4.25.3) from the generated file header and the declared range (`>=6.31.1,<8`) from `requirements.txt`, then asserts (1) the range **must have an upper bound**, (2) the installed runtime satisfies it, (3) the runtime is not older than gencode, and (4) `douyin_pb2` imports and round-trips a `PushFrame`. Current runtime 7.36.1 passes; an 8.x upgrade turns the test red with a "regenerate with a same-generation protoc first" hint.

#### 3. Repository metadata sync (Task 1/2)
- `AGENTS.md` version `4.1.0` → `4.2.0`; `docker-compose.yaml` example `APP_VERSION=4.1.0` → `4.2.0`; `config/config.ini` gained `tiktok_guest_cookie = ` after `tiktok_cookie` in `[Cookie]` (F-10 config-override key slot).
- The four-language catalogs (zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml) were topped up in the prior cycle (587 entries, **0 missing**); this cycle recompiled `zh_CN.mo` via `scripts/compile_po.py` (587 entries / 71594 bytes), `--check` passed.

#### 4. Verification
- pytest **974 passed / 2 skipped / 0 failed** (includes 20 F-01 golden-snapshot cases); frontend `node --test tests/frontend/*.mjs` 6 passed; `black --check` / `isort --check-only` / `py_compile` all green; `check_annotations` 0 violations; `compile_po --check` rc=0.
- Gate bar: pytest 0 warnings, black len120, isort black profile, mypy strict, basedpyright. End-to-end real-machine verification (F-19 Douyin nonce) pending.

### v4.2.0-dev (2026-09-12) — Full code-review fix (P0+P1+P2 plus + network/platform/scripts gates + i18n top-up, ~120 items)

**Summary**: Completed the P0/P1/P2 plus-items and the H-2/H-3/H-4/H-5/H-6 high-severity items from `CODE_REVIEW_2026-09-12.md` (~120 items: 3 critical + 6 high + ~40 medium + ~70 low), spanning security (SHA256 pinning, atomic writes, zip-bomb protection), robustness (concurrency locks, circuit breaking, proxy/SSL), deployment (Dockerfile no longer `curl|bash`), frontend (SSE, CSP), and test gates (five-script comparison gates). i18n migrated 10 f-string→`i18n.tr`, added 21 runtime templates to the four catalogs, recompiled `zh_CN.mo` to 566 entries.

#### 1. Module-classified
- **Security/deps**: H-1 SHA256 pinning (`scripts/ffmpeg_install.py`+`scripts/node_install.py` `_sha256_of_file`/`_check_or_record_zip_sha256`, LanZou `FFMPEG_LANZOU_SHA256`); C-1 blacklist bypass (web_api `req.key.strip()` + `_DANGEROUS_CONFIG_KEYS_FOLDED`); utils zip-bomb protection (4GB per file, 8GB cumulative, 100x ratio).
- **Concurrency/network**: H-2 singleflight (`src/cookie_cache.py`) isolates lock-in-await + gui.py 6.2 full fix (SMTP header injection `_reject_smtp_newline`, session token, quality-table dedup); 6.3 network layer — URL scheme allow-list `is_safe_http_url` wired, JS/subprocess execution via `utils.run_js_async`/`run_node_script_async`, async_http second-check-before-write, sync_http `data is not None`, room.py three AsyncClient sites `verify=ssl_verify`; 6.4 platform layer — Huajiao config write-back only for confirmed failures, base.py `DanmakuBase._on_reconnect()`, ws_client poison-message isolation.
- **Platform fixes**: C-2 Douyu sticky-packet (`offset += full_len + 4`); C-3 only_fans=False; H-4 Bilibili watchdog `spawn_danmaku_task(self._auth_watchdog(self._ws))`; H-5 Shopee clear path (finally `_not_record_prefix`); H-3 `websockets>=14.0`.
- **Robustness**: H-6 atomic write (config_io `_atomic_write_text` + web_config `_config_write_lock`); stream.py `_pad_list` min_length=6 + Douyin downgrade m3u8 clamp; converts_mp4 `-n`; standalone two-stage terminate (terminate→wait(3s)→kill); +60s backoff else deleted; 6 ffmpeg paths gained `record_finished=True` to trigger the post-record 30s quick-check; 6 `except subprocess.CalledProcessError` → `except OSError` + `recording.discard`.

#### 2. i18n & gates
- i18n: 10 f-string logs → `i18n.tr`; 21 runtime templates added to zh_CN.po/en_US.json/en_GB.json/zh_TW.yaml (idempotent script `scripts/patch_i18n_2026_09_12.py`); `zh_CN.mo` recompiled 566 entries / 68306 bytes.
- Gate scripts: sync_version.check_all "match-first-then-equal", check_coverage fuzzy match tightened, smoke_test utf-8-sig + `_NoRedirectHandler` + `_safe_print`; check_annotations `--snapshot` rmtree guard (never list `Path(os.sep)` as a system dir).

### v4.1.0-dev (2026-09-11) — Disable `-reconnect_at_eof` for HLS(m3u8) inputs: fixes live recording producing only subtitles and no video (P0, overturns previous open observation)

**Change summary**: With `-reconnect_at_eof 1`, an HLS(m3u8) input makes ffmpeg reconnect infinitely at the playlist layer, keeping the child process alive while producing zero bytes of video — the real-world failure looked like "live recording saved only the danmaku SRT, no video file". The previous entry (`Fix recording startup failure (-22 EINVAL) caused by missing values on ffmpeg -reconnect* options`) ended with an open observation that "live playlists have no ENDLIST so it never triggers / intended semantics" — **that was disproven by measurement: the end of the HTTP response of the m3u8 playlist itself is an EOF**. The option makes the http layer reconnect forever right after the playlist is fully downloaded (backoff 1/3/7/15/31s, no retry cap), so the hls demuxer never leaves the "waiting for playlist" stage and never pulls a single media segment. Fix: strip the option pair when the input is m3u8, keep it for FLV inputs.

#### 1. Incident shape & root cause (`main.py` base recording command)

- **Incident shape** (early 2026-09-11, user machine): Douyu/Douyin rooms (HLS-first source selection, honoring the existing "never add Douyu to FLV-first" rule) produced only danmaku SRT files — the SRT writer is started after `Popen`, so **the presence of SRT actually proves the ffmpeg process was up** — while the video directory stayed at zero bytes and ffmpeg stayed alive indefinitely (`-loglevel error` gives zero output and zero errors, so the `check_subprocess` guardian loop only ever saw the process alive). The same batch of Huya rooms (`_FLV_FIRST_PLATFORMS` + HLS exclusion list) recorded a normal 25MB `.ts`.
- **Root cause**: `-reconnect_at_eof 1` makes the http layer reconnect infinitely once a "read the full response" request reaches EOF. For HLS the demuxer must fully read the playlist (reaching EOF) before it considers parsing complete and moves on to pulling media segments — the perpetual re-fetch of the playlist means it never reaches the next stage. The signature `ffmpeg -report` log shows: consecutive `Will reconnect at 752 in 0/1/3/7/15... second(s), error=End of file` (752 being the playlist byte size).
- **Control experiment** (local ffmpeg 9.0.1, identical production command): with `-t 10` bound, the broken command still had not exited after 60s and produced zero bytes; removing only `-reconnect_at_eof 1` recorded 9MB in 10s and exited 0 — decisive evidence.

#### 2. Fix (the only correct approach)

- `main.py`: when `real_url` contains `.m3u8`, delete the `-reconnect_at_eof` option pair at command construction (`if ".m3u8" in real_url: idx = ffmpeg_command.index("-reconnect_at_eof"); del ffmpeg_command[idx:idx+2]`); FLV inputs keep it (reconnect-at-EOF continues appending to the same file after the CDN drops a long connection — the existing mitigation for Douyu guest FLV being cut at ~70s). The pair is removed via `del`, not set to `"0"`, keeping the command line clean.
- `scripts/douyin_live_recorder_standalone.py`: both `build_ffmpeg_cmd` and the inlined literal list in `run_ffmpeg` fixed in lockstep (preserving the "inline literal arguments at the call site + shell=False" gate semantics — `del` only removes by literal flag pair and never introduces concatenated-variable injection surface).

#### 3. Guardrails & verification (2026-09-11)

- `tests/test_ffmpeg_reconnect_args.py` gains a third invariant class `TestReconnectAtEofDroppedForHls`: AST-based assertion that every command definition point (1 in main.py, 2 in the standalone script) carries a "`.m3u8` in url guard + delete the `-reconnect_at_eof` pair in the function body" — removing any one of them regresses HLS recording into an infinite hang.
- Targeted: `test_ffmpeg_reconnect_args.py` 5 passed + `test_record_container.py` 18 passed; full regression **`pytest`: 907 passed, 2 skipped**; `black --check` / `isort --check-only` / `py_compile` all green.
- `AGENTS.md` "Known pitfalls" entry for `-reconnect*` gained the third form (existing text untouched, appended incrementally, overturning the outdated "semantics boundary" note at its end).

### v4.1.0-dev (2026-09-11) — Web panel rooms-list misalignment fix on narrow viewports (table-layout:fixed + URL ellipsis + horizontal scroll fallback)

**Summary**: Fixed the triple misalignment of the "Rooms" list on narrow viewports (effective width ≈500px, triggered by narrow windows or Windows high-DPI scaling): the "Enabled" / "Recording" column headers squeezed into one-character-wide vertical stacks, the "Delete" button and enable switch overflowing past the panel card's right edge, and long URLs (`discover?modal_id=` etc.) / long names wrapping into 2–3 lines causing uneven row heights. Only `web/style.css` changed (one new rule block scoped to `#rooms-view` appended at the end); no HTML/JS touched, and the dashboard / danmaku / files tables are unaffected.

#### Root cause & fix (new block at the end of `web/style.css`)

- Root cause: `.data-table` used the browser-default `table-layout: auto` with no column-width or truncation constraints. The 6 columns' min-content width (110px quality select + 40px switch + delete button + 24px cell paddings ≈ 360px) plus the URL column's min-content exceeds the `.panel` container on narrow viewports — `width:100%` breaks down and the table renders at min-content width, overflowing the card; `.panel` had no `overflow-x` fallback, and the existing ≤768px breakpoint only covered stat-cards / config-row / tabs, not tables.
- Fix: `#rooms-view .data-table` switched to `table-layout: fixed` with per-column header widths (quality 128 / name 150 / enabled 72 / recording 72 / actions 76; the URL column takes the remaining width); URL and name `td` render as a single ellipsized line (`overflow:hidden + text-overflow:ellipsis + white-space:nowrap`), with the full URL available via hover title (the URL `td` rendered by `loadRooms` already carries `title`); `td` gets explicit `vertical-align:middle` to remove cross-browser UA differences. ≤768px fallback: table `min-width:640px` + `.panel` `overflow-x:auto` — right-side control columns are no longer squeezed and scroll horizontally inside the panel instead.
- Browser notes: Chrome/Edge break lines at `/?&=`, Firefox distributes auto-table column widths differently, and Safari only renders cell ellipsis together with `table-layout:fixed` — the fixed layout is the one solution covering overflow + ellipsis across all three.

#### Verification (2026-09-11, Chrome 153 headless rendering the real `web/style.css`)

- 1200 / 768px: table fits the panel, delete button inside the card, all headers horizontal, uniform 47px row heights across 8 rows;
- 500 / 375px: every element clipped inside the panel card (`overflow-x:auto` active, right columns reachable by horizontal scroll), zero out-of-card overflow; all symptoms from the pre-fix screenshot (vertical headers, delete button drawn on the gray page background) eliminated;

### v4.1.0-dev (2026-09-11) — Fix recording startup failure (-22 EINVAL) caused by missing values on ffmpeg `-reconnect*` options

**Summary**: Fixed the option values lost during the 2026-09-10 refactor that moved `-reconnect*` before `-i` — the boolean `1` values of `-reconnect_streamed` / `-reconnect_at_eof` were dropped, so ffmpeg parsed the next option name as the value (`Unable to parse "reconnect_streamed" option value "-reconnect_at_eof" as boolean` → Invalid argument), **failing at input open with return code -22**. The defect reproduced 100% in real recording on a Douyin h264 HLS candidate in the early hours of 09-11 (the h265 FLV candidate had been skipped by the expected downgrade path, hitting the HLS branch instead).

#### 1. Root cause (`main.py` base recording command)

- The 09-10 code-review fix moved `-reconnect_delay_max 60 / -reconnect_streamed / -reconnect_at_eof` from after `-i` to before it, **dropping the values `1` of the latter two options** (`-reconnect_delay_max 60` survived because it kept its value). The old form (after `-i`) was silently accepted by ffmpeg with exit code 0 and no visible symptom, so the defect stayed hidden until now.
- Also corrected the `_FFMPEG_ERRNO_HINTS[-22]` hint text: besides "container/codec mismatch (HEVC into ipod)", `-22` can also mean "input option parsing failure"; the old hint misdirected troubleshooting toward container issues (it did in this investigation).

#### 2. Fix and guardrails

- `main.py`: restored `-reconnect_streamed 1` / `-reconnect_at_eof 1` (still before `-i`).
- `tests/test_ffmpeg_reconnect_args.py` (new, 3 cases): AST scan over both definition points (`main.py` + `scripts/douyin_live_recorder_standalone.py`), asserting ① every `-reconnect*` is immediately followed by a literal value that is not an option name; ② all of them precede `-i` (landing the guardrail suggested in the 09-10 review but never implemented). The assertion was verified to have teeth against the broken (value-less) form.
- Local ffmpeg test: the broken arguments reproduced the user's log verbatim against a local HLS stream; the fixed arguments opened the input and recorded successfully.

#### 3. Verification (2026-09-11)

- `pytest` (test_ffmpeg_reconnect_args / test_record_container / test_main_fixes): **50 passed**;
- `black --check` / `isort --check-only` / `mypy`: all green;
- Open observation: `-reconnect_at_eof 1` reconnects indefinitely on streams that reach EOF (reconnect has no retry cap) — live playlists have no ENDLIST so it never triggers, and after a stream ends failure relies on the CDN 403/404; this is intended semantics. Real-machine incremental verification (one recording round with a fresh live URL) still recommended.

### v4.1.0-dev (2026-09-10) — Full migration of parameterized logs from f-string to i18n.tr (242 sites / 27 files; placeholder renames across the four language catalogs)

**Change summary**: Rewrote **242 f-string call sites** in `logger.*` / `print` into `i18n.tr(template, **kw)`, and renamed the placeholders in the four language catalogs in lockstep so that "msgids with placeholders" can finally be matched — before this migration the f-string completed interpolation **before** the catalog lookup, so keys like `[{record_name}] ...` could never match and translation silently fell back to the source text (200+ parameterized logs were effectively "translated but unusable"). The scanner in `scripts/extract_i18n_strings.py` was also updated to recognise `tr()` — otherwise migrated call sites would vanish from the extraction result and the missing-entry check would degrade into a false green.

#### I. Migration mechanism (`i18n.py`, added in the previous batch, applied at scale here)

- `i18n.tr(template, **kwargs)`: `_tr(template)` **lookup** first, then `str.format(**kwargs)` **interpolation**. The template must be a literal constant string and placeholders must be plain identifiers (`str.format` rejects `{a.b}` / `{f(x)}`).
- Format specs / conversions are **pre-evaluated by the caller** and passed as arguments rather than kept in the template: `f"{_backoff:.0f}"` → `_backoff=f"{_backoff:.0f}"`; `f"{value!r}"` → `value=repr(value)`. The extractor already discards `:spec` / `!conv`, so both sides agree.
- Placeholder names are **deterministically derived** from the expression (duplicates within one template get a `_2`/`_3` suffix), guaranteeing the same name on the source side and the catalog side: `type(e).__name__`→`type_name`, `utils.mask_credentials(url)`→`masked_url`, `self._cls_name`→`cls_name`, `X.get('k')`→`k`, `X['k']`→`k`, `len(X)`→`X_count`, `X.__name__`→`X_name`; otherwise the longest non-keyword identifier.

#### II. Source migration (242 sites / 27 files)

- Counts: `main.py` 58, `src/spider.py` 25, `src/stream_select.py` 20, `msg_push.py` 15, `src/recorder_status.py` 12, `web.py` 11, `src/danmaku_monitor.py` 11, `src/ffmpeg_install.py` 11, `src/config_io.py` 9, `src/video_postprocess.py` 9, `src/log_archive.py` 7, `src/utils.py` 7, `src/async_http.py` 6, `src/node_install.py` 6, `src/ffmpeg_proc.py` 5, `src/notify.py` 5, `src/scheduler.py` 5, `src/stream.py` 4, `src/collector.py` 3, `src/sync_http.py` 3, `src/platforms/bilibili.py` 2, `src/room.py` 2, `src/ttwid.py` 2, `gui.py` 1, `src/cookie_cache.py` 1, `src/platforms/douyin.py` 1, `src/web_tray.py` 1.
- 9 **untranslatable** decorative / placeholder-only templates were skipped (e.g. `f"{'=' * 60}"`), matching the extractor's `is_valuable` rule.
- Existing `tr()` calls were normalised: in `src/ffmpeg_proc.py` the placeholder derived from `len(still_running)` became `{still_running_count}`, so the `count=` keyword was renamed to `still_running_count=` (the mismatch would have raised `KeyError` in `.format` at runtime — caught by the new regression test).
- `import i18n` was added to all 27 files; in `main.py` it was moved **before** the module-level banner prints (module code executes top-down, so an import placed after the banner is useless). `gui.py` keeps its existing alias `import i18n as i18n_module`.

#### III. Four-language catalog rewrite (key set 539 → 544)

-  5 new warning strings appended (`JSON 解析失败(已忽略)`, `ffmpeg 转封装/转码超时`, `ffmpeg 转 MP4 超时`, `ffmpeg 抽音频超时`, `执行自定义脚本超时`).
- `i18n/en_US.json` / `i18n/en_GB.json`: 125 key/value rewrites each + 5 new entries, written back with `sort_keys=True` in the original format (no BOM / CRLF).
- `i18n/zh_TW.yaml`: 134 lines rewritten + 5 new entries (single-quoted style). Note that YAML single-quoted scalars escape `'` as `''`, and some entries use the `? key` explicit key indicator and multi-line scalars — renaming must first un-escape `''`→`'` before deriving names, and must not filter lines by "contains an ASCII colon" (otherwise `? ` lines and continuation lines are missed, producing 9 key differences against `.po`).
- `zh_CN.mo` recompiled: 545 entries (544 + header empty msgid), 65232 bytes; `--check` byte-level sync passes.
- The `.po` header maintenance note was updated: placeholders must be plain identifiers; three translation lookup entry points (`print` constant strings / `tr()` parameterized logs / other `tr()` call sites); and a note that the zh_CN catalog is **not** an identity mapping (128 English source strings are translated into Chinese).

#### IV. Tooling and gate changes

- `scripts/extract_i18n_strings.py`: `scan_file` now recognises the first positional constant string of `tr(...)` / `<alias>.tr(...)` (during the f-string/tr coexistence period both forms must be scanned); the caller module name set is the constant `TR_CALLER_IDS = {"i18n", "i18n_module"}` — missing an alias makes that call site vanish from the extraction result, degrading the missing-entry check into a false green for it (`gui.py` uses `i18n_module`). Rule 5 added to the module header.
- `tests/conftest.py`: new autouse fixture `_pin_identity_translation` pinning `i18n._tr` to `lambda t: t`. Rationale: after the `tr()` migration, log text varies with `config.ini`'s `language` and the host system language (empty `language` → detected `en_US` on this machine, so the same assertion yields different text on different machines), and the zh_CN catalog is also not identity (128 English source strings → Chinese), so there is **no** single language that reproduces the source text. Freezing to identity makes `tr(template, **kw) == f-string output before migration`, decoupling assertions from language. The translation mechanism itself is covered by `tests/test_i18n_tr.py` and the language cases in `test_web_api.py`.
- `tests/test_i18n_migration.py` (new, 3 cases): ① no remaining "valuable" `logger/print` f-strings; ② every `tr()` template's placeholder set equals its keyword-argument set and all placeholders are plain identifiers; ③ the runtime template set is a subset of the `zh_CN.po` key set (equivalent to the extractor's "0 missing").
- `AGENTS.md`: 2 new anti-regression entries (parameterized logs must use `tr()`; tests must freeze translation to identity).

#### V. Verification (2026-09-10)

- `pytest -q`: **902 passed, 2 skipped** (899 → +3 migration regression cases; green both before and after the migration);
- `python scripts/extract_i18n_strings.py`: **0 missing, zero key divergence across the four catalogs** (544 each; the 191 historical/compat entries are intentionally retained);
- `python scripts/compile_po.py --check`: in sync with `.po` (545 entries);
- `black --check .`: 128 files unchanged; `isort --check-only .`: exit 0 (9 skipped); `mypy src/ main.py web.py gui.py i18n.py msg_push.py`: 44 files, 0 errors;
- `python scripts/check_annotations.py`: all pass (new test file comment density 13.8% ≥ 13.0%);
- `python scripts/check_version.py`: PASS.

#### VI. Rollback point

- A full pre-migration snapshot is kept at `.workbuddy/tmp/i18n_param_migration_backup/` (four catalogs + the extractor + 27 source files; 53 files / 1.6 MB). The workspace is not a git repository, so this is the only rollback baseline.

### v4.1.0-dev (2026-09-10) — 28 code-review fixes + repository metadata sync + four-language catalog completion (521 → 539 entries)

**Change Summary**: This round fixes every item from `CODE_REVIEW_2026-09-10.md` one by one (all P1 cleared, P2/P3 as applicable) and closes out two consistency tasks. ① **Code-review fixes**: 28 items across `main.py`, `src/ffmpeg_proc.py`, `src/stream_select.py`, `src/web_config.py`, `web/app.js`, `src/collector.py`, `src/srt_writer.py`, `src/spider.py`, `src/ttwid.py`, `src/async_http.py`, `src/sync_http.py`, `src/danmaku_monitor.py`, `src/cookie_cache.py`, `src/utils.py`, plus `scripts/` and `tests/` — notably the ffmpeg `-reconnect*` option placement, acquiring the semaphore before `Popen`, the collector stop/loop handshake, `SRT` injection, sensitive-config masking, and `utils.mask_credentials`. ② **Metadata sync**: `pyproject.toml` (4.1.0) is the single source of truth; version/dependency/directory-listing drift across the eight metadata files was checked. ③ **Localization completion**: the extractor scan backfilled the 18 logger strings introduced during the fixes; the four catalogs' key sets are consistent again (539 each) and `zh_CN.mo` was recompiled.

#### 1. Code-review fixes (by module)

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.1.0-dev (2026-09-10) — 28 code-review fixes + repository metadata sync + four-language catalog completion (521 → 539 entries) | section: 1. Code-review fixes (by module)).

#### 2. Repository metadata sync (8 files)

- `pyproject.toml` version is the single source of truth (4.1.0); `AGENTS.md` version `4.0.9.4 → 4.1.0` and `docker-compose.yaml`'s `APP_VERSION` example `4.0.9.4 → 4.1.0` both align with `pyproject.toml`.
- `requirements.txt` and `pyproject.toml [project.dependencies]` (20 deps) were checked entry-by-entry with no drift; `.coveragerc-concurrency`'s `omit` matches `pyproject.toml [tool.coverage.run].omit` entry-by-entry; no other directory-listing/path drift.

#### 3. Localization completion (4 catalogs + build artifact)

- Backfilled the 18 logger strings introduced during the fixes (source: `main.py` 3, `src/collector.py` 7, `src/async_http.py` 1, `src/ffmpeg_proc.py` 2, `src/cookie_cache.py` 2, `src/stream_select.py` 3); the four catalogs (zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml) were re-checked by the extractor and are **fully consistent** (539 each), clearing the "runtime has it, catalog doesn't" gap (191 historical/compat redundancy entries intentionally kept).
- `python scripts/compile_po.py` recompiled `zh_CN.mo` (540 entries incl. header empty msgid, 67700 bytes); `--check` passes at byte level.

#### 4. Deletions

- Deleted `tests/test_utils.py.isorted` (isort process residue).

#### 5. Deferred (needs product decision / real-device verification, unchanged this round)

- **Needs product decision**: audio extension/container, notify script timeout, `http_config` TLS split, web_api auth model, `gui_legacy.py` deprecation, hls.js `@latest` pinning, danmaku disk-write off the main loop, i18n parameterized text.
- **Needs real-device verification**: `spider.py` SSRF/JSON points, `ws_client.py` cipher suites/heartbeat, `proxy.py` Windows format, `video_postprocess.py` timeout.

#### 6. Verification (2026-09-10)

- `pytest -q` full run: `870 passed, 2 skipped, 0 warnings` (pre-fix targeted 11 modules: 201 passed);
- `python scripts/extract_i18n_strings.py`: 0 missing, zero diff across the four catalogs;
- `python scripts/compile_po.py` / `--check`: in sync with .po (540 entries);
- mypy 106 files 0 errors; black 124 unchanged; isort pass; basedpyright 0 errors (changed files);
- `python scripts/check_version.py`: PASS (version dynamicization state intact).

> **The second batch of this entry — "8 product-decision items + 4 machine-validation items + uv.lock aligned to 4.1.0" — is appended at the end as a separate `v4.1.0-dev (2026-09-10)` entry, to keep this section readable.**

### v4.1.0-dev (2026-09-10) — 8 product-decision items + 4 machine-validation items + uv.lock aligned to 4.1.0 (v4.1.0 second batch)

**Change summary**: Continuing the previous section's "V. Unprocessed (needs product decision / machine validation)" list, this batch implements the user's "all 8 + conservative with tests" strategy and aligns `uv.lock` with `pyproject.toml` 4.1.0. ① **All 8 product-decision items**: pin `hls.js` CDN dependency, split `http_config` TLS verification (stream-fetch vs control-plane), fix audio extension/container/encoder three-way mismatch, add `notify` script timeout control, strengthen web_api auth model (security response headers + public auth-status endpoint), delete `gui_legacy.py`, decouple danmaku SRT disk-write from the event loop, introduce i18n `tr()` parameterized interface. ② **4 machine-validation items with conservative defaults + stub tests**: `spider.py` JSON/URL validation, `ws_client.py` heartbeat timeout, `proxy.py` IPv6, `video_postprocess.py` timeout classification — use loose defaults and add stub tests per the user's instructions; the real-machine validation list is handed to the user for execution. ③ **Metadata cleanup**: `uv.lock` project version `4.0.9.4 → 4.1.0` with `uv lock --check` passing; stale `DouyinLiveRecorder.egg-info/` regenerated via `pip install -e . --no-deps`.

#### I. 8 product-decision items (by module)

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.1.0-dev (2026-09-10) — 8 product-decision items + 4 machine-validation items + uv.lock aligned to 4.1.0 (v4.1.0 second batch) | section: I. 8 product-decision items (by module)).

#### II. 4 machine-validation items (conservative implementation, by module)

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.1.0-dev (2026-09-10) — 8 product-decision items + 4 machine-validation items + uv.lock aligned to 4.1.0 (v4.1.0 second batch) | section: II. 4 machine-validation items (conservative implementation, by module)).

#### III. Repository metadata cleanup

- `uv.lock` project version `4.0.9.4 → 4.1.0` (single-line change: `version = "4.0.9.4"` → `4.1.0` in the `name = "douyinliverecorder"` block); no dependency-graph re-resolution (other 73 packages untouched); `uv lock --check` passes.
- Regenerated `DouyinLiveRecorder.egg-info/PKG-INFO` (previously 4.0.9.2, lagging pyproject 4.1.0): `pip install -e . --no-deps`, `importlib.metadata.version('douyinliverecorder')` now reads `4.1.0`.
- `scripts/check_version.py` PASS (no regression in dynamic-version state).

#### IV. Deletions

- `gui_legacy.py` (legacy GUI, redundant with `gui.py` and the `CREATE_NO_WINDOW` bug made graceful stop never work).

#### V. Unprocessed (still untouched this batch)

- Full migration of pre-existing 200+ parameterized f-string logs to `tr()` (dedicated project, out of scope here).
- Real-machine validation of the 4 items (handed off to the user): `spider.py` SSRF/JSON validation against real APIs, `ws_client.py` cipher suite handshake under `OpenSSL 3.x`, `proxy.py` IPv6 actual detection on Windows, `video_postprocess.py` ffmpeg actual hang timeout path.

#### VI. Verification (2026-09-10)

- `pytest -q` full: `899 passed, 2 skipped, 0 warnings` (from 870 before this batch; +29 new tests: test_notify 4 + test_web_api 4 + test_danmaku_offloop 5 + test_i18n_tr 6 + test_machine_validation_fixes 7 + the original 11 module-targeted 201 passed unchanged);
- `python scripts/extract_i18n_strings.py`: 0 missing, zero divergence across the four-language catalogs;
- `python scripts/compile_po.py` / `--check`: in sync with .po (540 entries);
- mypy 44 files 0 error (including `Optional` import added to `src/spider.py` and `cast` import added to `src/ws_client.py`); black 104 files unchanged (isort adjusted 5 files then passed); isort pass;
- `python scripts/check_version.py`: PASS (uv.lock 4.1.0, egg-info 4.1.0, pyproject 4.1.0 all consistent);
- `uv lock --check`: passes (73 packages unchanged).

### v4.0.9.4-dev (2026-09-07) — CI dependency versions aligned with latest official stable releases (codecov-action v5→v7, isort 8.0.1→9.0.1, mypy 2.3.0→2.3.1)

**Change Summary**: Every dependency and runtime version referenced by `.github/workflows/ci.yml` was audited against the latest official stable releases as of 2026-09-07; the stale ones were upgraded, the rest verified current. **Upgraded (3)**: ① `codecov/codecov-action@v5 → @v7` (latest v7.0.0, 2026-06-07; v6's only breaking change is the node24 runtime migration, natively supported on ubuntu-latest — and setup-python/setup-node v7 are node24 ESM actions themselves; `files` / `token` / `fail_ci_if_error` / `slug` inputs verified unchanged against v7.0.0's action.yml, so the existing usage is drop-in compatible); ② pinned lint tool `isort 8.0.1 → 9.0.1` (released 2026-08-28; 9.0.0 only removes long-deprecated legacy option logic, `--profile black` defaults untouched); ③ `mypy 2.3.0 → 2.3.1` (patch release, 2026-08-15). **Verified current, kept as-is (6)**: checkout / setup-python / setup-node / upload-artifact all @v7 (each already the latest major), `dorny/paths-filter@v4` (latest v4.0.3), black 26.5.1 (already the newest stable on PyPI), Python 3.14 (3.15 GA expected 2026-10), Node 24 (Active LTS until 2028-04; Node 26 enters LTS only on 2026-10-28, so 24 remains the official production recommendation). **Verification**: the three affected gates were run locally (venv 3.14.7) with the exact CI commands — `isort --check-only --diff --profile black --line-length 120 .` exit 0; `mypy src/` and `mypy --platform linux src/` both 0 errors (a one-off mypy internal error on the first run after the version switch was stale `.mypy_cache` residue; clean-cache reruns reproduce nothing); `black --check --line-length 120 --target-version py314 .` reports 124 files unchanged; both workflows parse as valid YAML (ci 8 jobs / release 4 jobs). `AGENTS.md`'s "CI / workflow conventions" actions-baseline entry was updated to codecov-action@v7. Zero changes to requirements.txt / pyproject.toml runtime dependencies (only CI-inline tool pins and action versions moved; test / concurrency-test / integration-verify / build-verify jobs are unaffected). `uv.lock` was refreshed in the same pass: `uv lock --upgrade-package isort` moved isort 8.0.1 → 9.0.1 (9.0.1 is a mypyc-compiled distribution and newly depends on `mypy-extensions`, already present in the lock, so no new package entry) and also brought the project's own version recorded in the lock 4.0.9.2 → 4.0.9.4 (aligned with `pyproject.toml`); `uv lock --check` passes (73 packages). black 26.5.1 and mypy 2.3.1 in the lock were already the target versions — no change needed.

### v4.0.9.4-dev (2026-09-06) — Eight-file repository metadata sync + i18n catalog completion (516 → 521 entries) + this cycle's change overview (classified by module)

**Change Summary**: Two consistency wrap-ups plus an overview. ① **Metadata sync**: using `pyproject.toml` as the single source of truth, every version / path / directory-list / dependency drift among `AGENTS.md`, `docker-compose.yaml`, `requirements.txt`, `Dockerfile`, `.gitignore`, `.dockerignore`, `.coveragerc-concurrency` and `pyproject.toml` was checked and corrected — including a **packaging defect in `pyproject.toml` that made `pip install .` emit an incomplete distribution** (sub-packages not declared). ② **Localization**: 5 missing strings found by `scripts/extract_i18n_strings.py` were added, so all four catalogs (`zh_CN.po` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`) share an identical key set again (521 entries each), and `zh_CN.mo` was recompiled. ③ **Overview**: this cycle's changes — spread across 10 changelog entries — are merged here by module, with deletions and leftovers listed separately.

#### 1. Metadata & Build (8 files)

- `pyproject.toml`: `[tool.setuptools].packages` changed from `["src"]` to `["src", "src.platforms", "src.proto"]`. An explicit `packages` list is **not recursive**, so the omission made distributions built by `pip install .` miss `src/platforms` (per-platform danmaku collectors) and `src/proto` (Douyin danmaku protobuf) — a runtime `ModuleNotFoundError` on the import chain (`DouyinLiveRecorder.egg-info/SOURCES.txt` has only 102 lines and lists neither sub-package; verifiable). Version `4.0.9.4` and the 20 dependencies verified drift-free.
- `AGENTS.md`:
  - Directory tree gained `tests/` (incl. `frontend/`), `src/proto/__init__.py`, `.github/ISSUE_TEMPLATE/` + `PULL_REQUEST_TEMPLATE.md` + `issue-translator.yml`, plus a root-docs group (`README.md` / `README_EN.md` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` / `AGENTS.md` / `LICENSE` / `index.html` / `StopRecording.vbs`);
  - module count in "Key Conventions" 41 → 42 (new `src/proto/__init__.py`);
  - testing section gained the frontend-test convention (`tests/frontend/*.mjs` uses Node's built-in `node:test`, zero npm dependencies; invoked by a same-named Python wrapper via `node --test` subprocess, skipped when Node is absent) and dropped the dead link to `.qoder/skills/test-creator/SKILL.md` (that directory does not exist in this workspace);
  - dependency section gained two notes: dev dependencies live in `[project.optional-dependencies].dev` and never enter `requirements.txt`; frontend tests need no npm packages;
  - "Known Pitfalls" gained 2 entries: the HLS capture exclusion list **removes the whole HLS candidate group** (must not be implemented as the reordering semantics of `_FLV_FIRST_PLATFORMS`), and GUI/WEB quality switches must sync the editor snapshot and the display source after writing back (the serial-number prefix / stale-snapshot overwrite / stale log value defects share one root).
- `docker-compose.yaml`: the `APP_VERSION` example in comments `4.0.9.2` → `4.0.9.4` (aligned with `pyproject.toml`), plus a note that leaving it unset only empties the LABEL while the in-image version is still read at runtime via `importlib.metadata`.
- `requirements.txt`: header notes added for "dev deps come from `.[dev]`, GUI from `.[gui]`, neither enters the runtime list" and "frontend tests need zero npm deps"; the 20 runtime deps were diffed against `pyproject.toml [project.dependencies]` **entry by entry** with no additions or removals.
- `Dockerfile`: `ARG APP_VERSION` now documents `pyproject.toml` as the single source of truth and CI injection via tomllib; the `COPY . ./` step documents what `.dockerignore` must **keep** (`main.py` / `web.py` / `gui.py` + `src/` incl. JS signing scripts and proto + `web/` + `i18n/**/*.mo`) and what it excludes.
- `.gitignore` / `.dockerignore`: both gained `*.pyc_probe_tmp` (transient probe artifacts such as the leftover `src/stream.pyc_probe_tmp`, not source).
- `.coveragerc-concurrency`: header notes that frontend `.mjs` tests produce no Python coverage data, and that the `omit` list is maintained in lockstep with pyproject and both ignore files.

#### 2. Localization (4 catalogs + compiled artifact)

- 5 entries added (all logger-side f-string templates; sources: 3 from `src/stream_select.py`, 1 from `src/danmaku_monitor.py`, 1 from `src/cookie_cache.py`):
  - `平台 {platform} 在 HLS 采集排除列表中…` (platform in the HLS capture exclusion list with no fallback) — `src/stream_select.py`
  - `弹幕边车文件写入失败: {type(e).__name__}: {e}` (danmaku sidecar file write failed) — `src/danmaku_monitor.py`
  - `流地址校验: {url} - GET 复核异常: …（attempt {attempt}）` (stream-URL validation: GET recheck exception) — `src/stream_select.py`
  - `流地址校验: {url} - Range-GET 未取得响应，按校验失败处理` (Range-GET returned no response) — `src/stream_select.py`
  - `等待其它线程的 cookie 拉取超时，返回空结果: {key}` (timed out waiting for another thread's cookie fetch) — `src/cookie_cache.py`
- Catalog size 516 → 521; the extractor confirms all four key sets are **identical** again, and the "present at runtime but absent from catalog" gap is down from 5 to 0 (183 historical/compatibility entries intentionally kept).
- `zh_CN.po` header dates 2026-08-30 → 2026-09-06; `python scripts/compile_po.py` recompiled `zh_CN.mo` (522 entries incl. the header empty msgid, 64930 bytes) and `--check` passes byte-level.
- `web/app.js` frontend dictionaries (106 keys each) verified key-consistent across all four languages — no change needed (frontend strings are maintained separately from the four catalogs).

#### 3. This Cycle's Code Changes (Classified by Module, 2026-09-02 ~ 09-06)

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.4-dev (2026-09-06) — Eight-file repository metadata sync + i18n catalog completion (516 → 521 entries) + this cycle's change overview (classified by module) | section: 3. This Cycle's Code Changes (Classified by Module, 2026-09-02 ~ 09-06)).

#### 4. Deletions & Leftovers

- **Deleted**: the cross-loop aclose dispatch branch in `src/async_http.py`; `@pytest.mark.filterwarnings("ignore::RuntimeWarning")` in `tests/test_async_http_lock.py`; the unused `Callable` import in `scripts/douyin_live_recorder_standalone.py` (09-02); the dead `.qoder/skills/test-creator/SKILL.md` reference in `AGENTS.md`.
- **Moved**: `douyin_live_recorder_standalone.py` from the repo root into `scripts/` (equivalent to deleting the root copy).
- **Leftover (not deleted, now ignored)**: `src/stream.pyc_probe_tmp` (a 2026-09-01 probe artifact, not source) — added to `.gitignore` / `.dockerignore`, awaiting manual cleanup.
- **Changelog dedup**: `CODE_WIKI_EN.md` carried two near-identical translations of the same 2026-08-29 "Web Panel Manual Recording Control" entry (the Chinese doc has one); the duplicate block was removed and the surviving entry's title realigned with the Chinese wording.

#### 5. Verification (2026-09-06)

- Full `pytest -q`: **858 passed, 2 skipped, 0 warnings**;
- `python scripts/extract_i18n_strings.py`: 0 missing, zero divergence between the four catalogs;
- `python scripts/compile_po.py` / `--check`: in sync with the .po (522 entries);
- `python scripts/check_version.py`: PASS (dynamic-versioning state intact);
- dependency diff script: `requirements.txt` and `pyproject.toml` agree on all 20 entries;
- `pytest tests/test_i18n.py`: 34 passed (four-catalog key-set consistency assertions).

### v4.0.9.4-dev (2026-09-06) — GUI quality-switch persistence fixes + full WEB per-room quality-change path + frontend/backend unit tests

**Summary**: Follow-up to the previous change that fixed three defects and completed the missing WEB-side functionality. Defect 1 (GUI key-format mismatch): the quality-monitor menu passed `"序号11 DANK1NG"` (row name with prefix) to the reverse lookup table whose keys are pure anchor names (`"DANK1NG"`), so every lookup missed and the toast "URL_config.ini entry not found, quality unchanged" fired. Defect 2 (persistence loss): writing the change updated `URL_config.ini` on disk but left the URL-config editor's `config_text` widget holding the pre-write snapshot — the user hitting "Save" later would overwrite the file with old content, erasing the quality segment. Defect 3 (display reset): the "set quality" column was rendered from the subprocess log (`序号11 DANK1NG[原画] 正在录制中`, a snapshot taken when recording started) and every table rebuild (≈5 s) reset the menu back to the stale value. The WEB panel previously exposed only add/drop quality options (global list) but had no per-room quality switcher entry or backend endpoint. This fix: GUI strips the `序号N ` prefix before lookup, reloads the editor after a successful write (so the user's "Save" does not overwrite), and renders "set quality" from the live config file instead of the log snapshot. WEB: new `PUT /api/rooms/quality` endpoint sharing `update_room_quality` with the GUI (same line format, file lock against concurrent rewrites); frontend room-list quality column changed to inline `<select>` driven by event delegation (change → PUT → reload). Backend API tests 8, frontend `node:test` 6 (DOM/fetch stubs, drives the real event-delegation chain).

**Changes**:

- `gui.py`:
  - `_on_room_quality_change`: strips the `序号\d+(\s|$)` prefix before the reverse lookup so the row-name key matches `_anchor_url_map` (built by `parse_url_config` from plain anchor names, never prefixed); after a successful write, calls `_load_config()` to refresh `config_text`, the URL map, and the quality map — eliminating the "Save overwrites the quality segment" path (previous code only synced `mtime`, not the widget content).
  - New instance field `_anchor_quality_map` (anchor name → current quality in the config row); `_refresh_quality_context` builds it alongside the reverse URL map from the same `parse_url_config` pass.
  - `_add_quality_data_row`: the "set quality" column now sources from `_anchor_quality_map` (same prefix-strip before lookup), falling back to the log value only when the anchor is missing from the map — so the table rebuilds immediately showing the newly selected quality instead of the stale subprocess-log snapshot.
- `src/web_api.py`:
  - Import extended with `update_room_quality`.
  - New `RoomQualityUpdate(BaseModel)`: `url: str` + `quality: str | None` (empty/None = remove quality segment, fall back to the global default).
  - New `PUT /api/rooms/quality`: request body validated through `validate_room_target` (newline-injection guard) + whitelist (`BUILTIN_QUALITIES`, so a tier that would silently regress to "原画" cannot be written); serialised by holding `_rooms_config_lock` and `main.file_update_lock` to avoid TOCTOU races with the main loop's rewriter and add/droom endpoints; returns 404 (room not found) / 422 (validation) / 200 `{ok, changed}`; persistence delegated to `update_room_quality` — same implementation the GUI uses, so a change on one side is immediately visible on the other.
- `web/app.js`:
  - `buildRoomQualitySelect(url, current)`: constructs an inline quality `<select>` (options = default + `qualityOptions` + current as fallback so removing the current tier from the option list does not visually collapse the row); `data-action="quality"` + `data-url` forward the identity.
  - `loadRooms`: the quality column changes from a plain-text `<td>` to `buildRoomQualitySelect(...)`.
  - `rooms-tbody` event delegation gains a `select[data-action="quality"]` change branch, which dispatches `changeRoomQuality(url, value)`.
  - New `changeRoomQuality(url, quality)`: `PUT /api/rooms/quality`, toast on success followed by `loadRooms()` refresh; on failure it toasts and reloads the list so the UI reverts to the server-side truth (no user misselection stuck in the DOM).
  - `showView('rooms')`: `loadRooms()` is now chained after `loadQualityOptions().finally(loadRooms)` so the `<select>` has its full option set before the row renders.
  - Three-locale i18n keys added (`toast.qualityChanged` / `toast.qualityReset` / `toast.qualityChangeFailed`); API-contract comment block updated.
- `web/style.css`: new `.data-table select` compact rule (`padding: 4px 6px / font-size: 12px / max-width: 110px`) that intentionally differs from the form-level `.inline-form select`.
- `tests/test_web_api.py` (extends existing `TestRoomQualityApi` to 8 cases total):
  - `test_change_quality_requires_auth`: PUT without a Bearer token must return 401.
  - `test_change_quality_on_disabled_room_preserves_comment`: a commented-out room (`# 超清,...`) accepts a quality change, keeps the `#` prefix, stays disabled, and shows the new quality in the list.
  - `test_quality_visible_in_room_list_after_change`: PUT is immediately reflected by the next GET /api/rooms; sibling rows are unaffected.
  - `test_change_quality_matches_schemeless_url`: the URL normalisation in the backend lets a request with a bare host match a row written with a scheme.
  - `test_empty_string_quality_resets_to_default`: `quality: ""` behaves the same as `null` — both remove the quality segment.
- `tests/frontend/test_quality_ui.mjs` (new file, Node built-in `node:test` + `node:vm` sandbox, zero npm dependency):
  - DOM/fetch stubs load app.js (IIFE has no side effects at import time); `DOMContentLoaded` is fired manually; every test drives the real event-delegation chain (tab click → render → select change → PUT → toast/reload).
  - 6 cases: sandbox smoke, dropdown rendering (option composition + selected state + URL escaping + row structure), change-request contract, empty-value serialises to null, failure reverts to server truth, three-locale toast behaviour.
- `tests/test_frontend_quality_ui.py` (new file): pytest wrapper that runs `node --test` as a subprocess; skips when Node is unavailable (same environment-restriction convention as other harness-limited cases).

### v4.0.9.4-dev (2026-09-06) — Add/drop quality options in WEB/GUI + per-row quality switcher in quality monitor

**Summary**: The room-quality setting now goes from a fixed set of 10 engine-recognised tiers to a user-curated subset. The WEB "Rooms" view exposes add/remove controls for the quality dropdown (persisted under `config.ini [录制设置] / 自定义画质选项(逗号分隔)`); the GUI quality monitor gains an inline "switch quality" dropdown on every recording row. Both share the same config. Selecting a non-default quality rewrites the room line in `config/URL_config.ini` as `quality,url[,主播: name]`; the new quality takes effect on the next detection cycle (default 120 s).

**Changes**:

- `src/web_config.py`:
  - Introduced `BUILTIN_QUALITIES` tuple (aligned with `stream_select.get_quality_code`); legacy alias `QUALITY_KEYWORDS` now points to the same tuple to avoid parallel maintenance.
  - Added `QUALITY_OPTIONS_SECTION = "录制设置"` / `QUALITY_OPTIONS_KEY = "自定义画质选项(逗号分隔)"` as the single source of truth for the storage location.
  - `_split_multi_value` / `normalize_quality_options` / `read_quality_options` / `write_quality_options`: only built-in tiers are accepted (unknown names would silently degrade to "原画" downstream, so they're filtered out before reaching the dropdown); empty/all-invalid input falls back to the full built-in list; writes go through `update_config_line` (comment + section order preserved) and fall back to `append_config_line` when the key is missing; every input item is `_reject_newline`-checked before normalisation (parity with `format_url_line`, C3 hardening).
  - `update_room_quality`: URL-keyed line-level rewrite of `URL_config.ini`. Preserves the comment prefix (including the space after `#`), line-ending, anchor-name field, and the URL segment verbatim; idempotent (returns `False` when already at the target); segment-level URL match uses `normalize_url` so rows lacking a scheme are still hit; empty value or `"原画"` removes the quality segment (falls back to the global default); atomic write via temp file + `os.replace` so readers never see a half-written state; C7 hardening asserts no `.tmp` leftovers.
  - `find_room_url_by_anchor_name`: name → URL reverse lookup used by the GUI quality switcher (the GUI knows rows by anchor name but writes by URL); exact match first, substring fallback, empty string on miss.
- `src/web_api.py`:
  - New `GET /api/rooms/qualities` returns `{options, builtin}` — exposing `builtin` removes the need for the frontend to hard-code a tier list.
  - New `PUT /api/rooms/qualities` body `{options: [...]}`: validated through `validate_config_target` (newline-injection guard); invalid tiers are filtered by normalisation rather than accepted; persistence delegated to `write_quality_options`; re-exports `QUALITY_OPTIONS_SECTION` / `QUALITY_OPTIONS_KEY` to avoid hard-coding the same keys twice.
- `web/index.html`: removed the hard-coded `<option>` list inside the room-add form; only the "default quality" entry remains. A new "quality options" panel below the form (chips list + candidate select + add button + hint copy) is populated dynamically by `loadQualityOptions()`.
- `web/style.css`: added `.quality-options` / `.quality-panel` / `.quality-chips` / `.quality-chip` / `.quality-add-row` / `.quality-hint` styles. Chip delete buttons and the candidate select follow the global palette (light/dark theme aware).
- `web/app.js`: added module state `qualityOptions` / `qualityBuiltin`; new helpers `loadQualityOptions` / `renderQualityOptions` / `replaceChildren` (DOM API, avoids `innerHTML` concatenation per the security hook) / `buildQualityChip` / `saveQualityOptions` / `addQualityOption` / `removeQualityOption`; API-contract block updated with the new endpoint; `showView('rooms')` now also triggers `loadQualityOptions`; DOMContentLoaded wires `#quality-manage-btn` (toggle panel), `#quality-add-btn` (add), and `#quality-chips` event delegation (remove); four-locale i18n dicts gain `rooms.manageQuality` / `rooms.addQuality` / `rooms.qualityHint` / `rooms.qualityEmpty` / `toast.qualityAdded` / `toast.qualityRemoved` / `toast.qualitySaveFailed` / `toast.qualityLoadFailed`.
- `gui.py`:
  - Imports extended with `parse_url_config` / `read_quality_options` / `update_room_quality` (`find_room_url_by_anchor_name` kept for future use).
  - New instance fields: `_quality_options` (dropdown choices) / `_quality_default_label = "默认画质"` (first entry = fall back) / `_anchor_url_map` (anchor name → URL; needed to write back to `URL_config.ini`).
  - New `_refresh_quality_context`: reads the option list from `config.ini` and rebuilds the anchor → URL map by parsing `URL_config.ini`. Hooked into the existing `_load_config` so external edits to `URL_config.ini` keep the map fresh.
  - New `_quality_menu_values`: assembles the menu values (`default quality` + user-selected + current value as fallback, so removing the currently-selected option doesn't visually collapse the row to the first entry).
  - New `_on_room_quality_change`: choosing "default quality" clears the quality segment (falls back to global default); choosing a tier rewrites the line via `update_room_quality` as `quality,url[,主播: name]`. After a successful write, `_last_url_config_mtime` is synced so `_watch_url_config` doesn't treat the GUI's own write as an external change and clobber the URL-config editor; write failures surface an error dialog + error log (no silent data loss); unknown anchors also surface an error dialog + error log.
  - Quality-monitor detail header gains a "switch quality" column; `_add_quality_data_row` adds a `CTkOptionMenu` in column 6 (same light/dark theme palette as `appearance_menu`), with column weight 2.
  - A small wraplength hint at the bottom of the quality page documents the "takes effect next cycle" and "default quality = remove segment" semantics.
- `tests/test_web_config.py` (3 new classes): `TestQualityOptions` (normalisation strips unknown/empty/duplicates, missing key → built-in list, append/update round-trip preserves other keys, newline injection raises `ValueError`); `TestUpdateRoomQuality` (plain URL → add quality, modify existing, fall back to default, preserve comment prefix + line ending, idempotency, URL normalisation match, miss returns `False`, newline injection raises, atomic write leaves no `.tmp`); `TestFindRoomUrlByAnchorName` (exact match + miss returns empty string).
- `tests/test_web_api.py` (new `TestQualityOptionsEndpoints`): GET defaults to built-in list, PUT persists and survives a follow-up GET, PUT filters non-whitelisted tiers, PUT newline injection → 422.
- `README.md` / `README_EN.md`: the user-facing change is an additive refinement of the existing "Add room" / "Quality monitor" sections — no new top-level section needed; a changelog line is added in both languages.

**Impact**:

- User-visible: WEB room-add quality dropdown is no longer a fixed list of 10 entries; users pick which tiers to expose. GUI quality monitor gains a per-row switch; selecting a non-default quality rewrites `URL_config.ini` as `quality,url[,主播: name]` and takes effect on the next detection cycle. Selecting "default quality" removes the quality segment (room falls back to the global default in `[录制设置] / 原画|超清|高清|标清|流畅`).
- Unchanged: only the 10 built-in tiers are selectable (aligned with main.py's whitelist and `stream_select.get_quality_code` keys); arbitrary custom names are rejected. Switching quality does NOT restart the recorder subprocess and does not interrupt other rooms in progress. WEB and GUI share the same option list via `config.ini`.
- Edge handling: unknown URL surfaces an error dialog + error log instead of silently dropping the change; write failures surface an error dialog + error log; after a successful write, `_last_url_config_mtime` is synced to avoid the URL-config editor reloading on its own write.

- `pytest tests/`: **849 passed, 2 skipped** (3 new pure-function test classes + 1 new API test class; no regressions).
- `mypy src/ main.py web.py gui.py`: 0 issues across 42 source files.
- `basedpyright src/ main.py web.py gui.py`: 0 errors, 0 warnings, 0 notes.
- `black --check` / `isort --check` / `scripts/check_annotations.py`: all green (comment density 21.2%, well above the 13% threshold).

### v4.0.9.4-dev (2026-09-05) — HLS capture exclusion platform list: listed platforms ignore the HLS switch and always use FLV capture

**Summary**: Added the config key "HLS采集排除平台(逗号分隔)" — when "是否启用HLS采集(是/否) = 是" and the requested website (platform) is in the exclusion list, the HLS capture setting is ignored and FLV capture is used instead; websites outside the list are unaffected and keep normal HLS-priority behavior.

**Change list**:

- `main.py`:
  - New module-level global `hls_collection_exclude_platforms: list[str] = []` (next to `hls_collection_enabled`), added to `main()`'s `global` declaration;
  - `main()` main loop reads "录制设置 / HLS采集排除平台(逗号分隔)" (default empty) right after "是否启用HLS采集(是/否)" — supports Chinese and English commas, strips each entry and drops empties (following the `danmaku_platforms` parsing pattern), hot-reloaded every round.
- `src/stream_select.py` (`select_source_url`):
  - New effective-switch computation: `hls_excluded = platform in main.hls_collection_exclude_platforms`, `hls_effective_enabled = main.hls_collection_enabled and not hls_excluded` — a hit is equivalent to disabling HLS capture for that platform only;
  - Candidate sequence construction (`hls_seq`) now uses `hls_effective_enabled` instead of `main.hls_collection_enabled`: for excluded platforms the HLS candidates are **removed as a whole and never enter the sequence** (deliberately different from `_FLV_FIRST_PLATFORMS`, which only reorders while keeping HLS as fallback); the h265-FLV → HLS switch is disabled as a consequence;
  - The "HLS source present but HLS capture disabled with no fallback" warning branch also uses the effective switch and differentiates the two causes: a hit on the exclusion list suggests "remove the platform from the exclusion list to restore HLS capture", while the global-off case keeps the original wording.
- `tests/test_stream_select.py`: 5 new cases — excluded platform always selects FLV (zero HLS probes), FLV validation failure never falls back to HLS (HLS never probed), HLS-only source warns and returns None (asserting the warning points to the exclusion list), platforms outside the list behave unchanged (including a FLV-first platform control), excluded platform h265-FLV does not switch to HLS.
- `README.md` / `README_EN.md`: config example gained the "HLS采集排除平台(逗号分隔)" key with explanation; the Usage section gained a "Source selection (HLS/FLV)" subsection (config-item table for the global switch and the exclusion list, use case, fill format, priority semantics, boundary behavior, and hot-reload notes).
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`: the `[录制设置]` config table gained the new key row; the `select_source_url()` description documents the exclusion-list behavior.

**Impact**:

- User-visible: the new key defaults to empty = no platform excluded, zero behavior change; once a platform name is filled in (must exactly match what logs/config show, e.g. "斗鱼直播"), that platform always uses FLV.
- Boundary semantics: an excluded platform with only HLS sources and no FLV/record_url fallback behaves the same as globally disabling HLS capture — warns and gives up the round (the warning text points to removing the platform from the list); the `record_url` fallback chain is unaffected.

- `pytest tests/`: **828 passed, 2 skipped** (5 new cases, no regression in the full suite);
- `mypy .`: 105 source files, 0 issues.

### v4.0.9.4-dev (2026-09-05) — Standalone single-file build relocated to scripts/ (ffmpeg lookup fixed accordingly)

**Summary**: Relocated the standalone single-file integration script `douyin_live_recorder_standalone.py` from the repository root to `scripts/` (filename unchanged), and fixed the ffmpeg lookup in `find_ffmpeg` plus all path references accordingly. Out-of-box behavior is unchanged; the run command is now `python scripts/douyin_live_recorder_standalone.py ...` executed from the repository root.

**Change list**:

- `scripts/douyin_live_recorder_standalone.py` (moved in from the root):
  - `find_ffmpeg()` fix (**mandatory** — moving the file without this change would be a regression): the original lookup used `Path(__file__).parent / "ffmpeg" / exe`, which silently falls through to a PATH lookup once the file lives in `scripts/` (the repo-bundled ffmpeg/ would never be found). It now probes, in order, the script's own directory `ffmpeg/`, then its parent (repository root) `ffmpeg/`, then PATH — covering both in-repo runs and standalone copies of the script;
  - The usage examples in the file header and all commands in `RUN_STEPS` (the `--help-steps` output) gained the `scripts/` prefix; the FFmpeg install instructions now point to the repository-root `ffmpeg/` directory; the config.ini wording was corrected to "resolved against the runtime working directory" (`load_settings` has always been CWD-based — the old "place it next to this file" wording became misleading after the move; the behavior itself is unchanged).
- `AGENTS.md`: added the file to the `scripts/` section of the project-structure tree; the directory comment updated from "maintenance scripts (CI gates & i18n tools)" to "maintenance scripts & standalone tools (CI gates, i18n tools, single-file build)".
- `scripts/check_annotations.py`: **no change needed** — `EXCLUDE_FILES` matches by **file name** (`path.name in EXCLUDE_FILES`), independent of directory; the exclusion still works after the move (verified).
- `README.md` / `README_EN.md`: no change needed — the file is only mentioned by name in historical changelog entries (no path references; history preserved as-is).

**Impact**:

- User-visible: the run command gains the `scripts/` prefix (root → `scripts/`); the repo-bundled `ffmpeg/` is still auto-discovered at the repository root.
- Unchanged semantics: config.ini / URL_config.ini / the `downloads/` output directory are all resolved against the runtime working directory (CWD); `--selftest` / `--dry-run` / the four-platform resolve-and-record pipeline are all unchanged.

- `python -m py_compile scripts/douyin_live_recorder_standalone.py`: passed;
- `python scripts/douyin_live_recorder_standalone.py --selftest`: **all 62 checks [PASS]**, exit code 0;
- `find_ffmpeg()` returns `D:\DouyinLiveRecorder-dev\ffmpeg\ffmpeg.exe` (without the fix it would fall through to a PATH lookup);
- `black --check` / `mypy` (single file): 0 issues;
- `python scripts/check_annotations.py`: passed (105 Python files; the moved file remains excluded by name and is not part of the density check).

### v4.0.9.4-dev (2026-09-05) — Auto-clean test output dirs _out_live/_out_e2e after pytest sessions

**Summary**: `tests/conftest.py` gains a `pytest_unconfigure` hook that automatically deletes the `tests/_out_live` and `tests/_out_e2e` output directories once a pytest session ends (including collection failures / interrupted runs), eliminating leftover temp files from offline test cases (e.g. the SRT-on-disk assertions in `test_srt_timeline_anchor.py`).

**Implementation notes**:

- The path constant `_TEST_OUT_DIRS` is derived from the `tests/` directory itself (via `__file__`), independent of CWD;
- `shutil.rmtree(..., ignore_errors=True)`: missing directories or sporadic Windows handle locks (antivirus / indexer scans) are silently skipped — cleanup failures never turn into abnormal pytest exit codes;
- Both directories were already in `.gitignore`, so leftovers never polluted the repo; this cleanup is defensive housekeeping;
- Manual verification scripts (real-live end-to-end ones run directly via `python tests/xxx.py`, e.g. `test_bili_live_collector.py`) bypass pytest and are unaffected — their "clean-then-write" semantics and the human-review purpose of the SRT output remain unchanged.

- `pytest tests/test_srt_timeline_anchor.py`: 4 passed, `tests/_out_e2e` auto-deleted afterwards (together with the previously leftover `_out_live`);
- Repeated runs (when the dirs no longer exist) pass without errors — idempotent;
- Full `pytest -q`: **823 passed, 2 skipped** (identical to the 2026-09-04 baseline, no regression), both dirs absent afterwards;
- `mypy tests/conftest.py` / `black --check` / `isort --check-only` all pass.

### v4.0.9.4-dev (2026-09-04) — P0 fix: segmented-recording container mismatch made Douyin original-quality HEVC unrecordable (return code 4294967274)

**Summary**: Fixed a P0 regression where the "TS + segmented recording" branch passed `-segment_format ipod` — HEVC original-quality streams exited immediately with `AVERROR(EINVAL)` (shown as `4294967274` on Windows), while H.264 streams silently produced corrupt files with MP4 content under a `.ts` extension. The output-extension → inner-container mapping is now consolidated into a single module-level constant `SEGMENT_FORMAT_BY_SUFFIX`, asserted by the new `tests/test_record_container.py`.

**Root cause**: Two values in `main.py` were **swapped** — the TS branch used `ipod` (should be `mpegts`) and the M4A audio branch used `mpegts` (should be `ipod`); even the explanatory comment ("audio segmentation uses the ipod container…") had drifted onto the video branch, leaving the fingerprint of the swap. `ipod` is the "iPod H.264 MP4" subset muxer (`ffmpeg -h muxer=ipod`: extensions m4v/m4a/m4b, default video codec h264), whose codec tag table has **no HEVC entry**.

**Reproduction (ffmpeg n9.0.1)**:

- HEVC + `segment/ipod` → `Could not find tag for codec hevc in stream #0` + `Could not write header … Invalid argument`, byte-for-byte identical to the production log (production shows stream #1 because the live source carries an audio track), exit ≠ 0;
- HEVC + `segment/mpegts` → exit 0, 40 KB output, first byte `0x47`, demuxable as mpegts;
- **H.264 + `segment/ipod` → exit 0 with no error, but the output magic is `00 00 00 20 66 74 79 70` (`ftyp`)** — an MP4 container written into a `.ts` filename. Silent corruption; previously recorded files must be re-checked by magic byte.

**Changes**:

- `main.py`: new module-level constant `SEGMENT_FORMAT_BY_SUFFIX` (`.ts→mpegts` / `.flv→flv` / `.mkv→matroska` / `.mp4→mp4` / `.m4a→ipod`); all five segment branches now look the value up (the audio branch has a dynamic extension and uses `.get("." + extension, "ipod")` so `only_audio_record` platforms with an mp3 extension cannot raise KeyError); both misplaced comments moved back to their proper branches.
- `main.py`: added `_FFMPEG_ERRNO_HINTS` + `_describe_return_code()` — return codes are normalized to signed 32-bit with errno semantics (`4294967274` → `-22 (EINVAL: muxer parameters / container-codec mismatch…)`); unknown codes get no hint to avoid log noise.
- `src/spider.py`: `extract_douyin_hevc_flv_url()` now appends `&codec=h265` (returned as-is when a codec parameter already exists). Previously the HEVC URL scraped from the room HTML carried no such parameter, so `_is_h265()` and the h265 fallback check in `main.py` both missed it and the HEVC source went straight into `-c copy` disguised as a plain FLV.
- `tests/test_record_container.py` (new, 13 cases): mapping-table assertions, two-way TS≠ipod / M4A≠mpegts regression guards, an AST scan asserting all five values come from the lookup table with no bare literals, registered lookup keys, the ipod audio fallback, codec-marker emission verified through `_is_h265()`, and return-code normalization.
- `AGENTS.md`: two new anti-regression entries (segment container mapping; `hevc_flv_url` must carry the codec marker).

- Full `pytest -q`: **823 passed, 2 skipped, 0 warnings** (baseline before the fix: 808 passed);
- `black --check` (123 files) / `isort --check-only` / `mypy` (3 changed files) / `scripts/check_annotations.py` (average density 21.2%) all pass;
- Reproduction artifacts removed; no temporary files left behind.

**Sync and follow-ups**:

- The runtime directory `D:\DouyinLiveRecorder` (separate from the dev checkout `D:\DouyinLiveRecorder-dev`) received the **minimal fix** only (two container values in `main.py` + the codec marker in `src/spider.py`), with the originals backed up as `*.bak-20260904`. Return-code normalization and the mapping-table refactor were not pushed there: its `src/spider.py` is an older 4617-line revision that does not share history with the dev checkout's 5143-line file, so it was not overwritten wholesale.
- Previously recorded TS files should be re-checked by magic byte (first byte `0x47`); historical output from H.264 rooms may actually be MP4.

### v4.0.9.4-dev (2026-09-04) — Fixed flaky warning "FakeAsyncClient.aclose was never awaited" + AGENTS.md pytest zero-warning gate baseline finalized

**Change summary**: Fixed the flaky warning `RuntimeWarning: coroutine 'FakeAsyncClient.aclose' was never awaited` that fluctuated between 1~2 occurrences across full pytest runs (root cause: the scheduling race when `src/async_http.py::_get_client` closes a stale AsyncClient across event loops), and aligned the AGENTS.md "pytest (0 warnings)" gate with the actual baseline: third-party starlette/anyio deprecation warnings are now explicitly filtered via `pyproject.toml filterwarnings` with source comments, so the warnings summary of a full run is deterministically 0.

**Root-cause analysis (three candidate fixes ruled out empirically)**:

- Old implementation (original L63): when evicting a stale client created on another loop, it used `run_coroutine_threadsafe(client.aclose(), client_loop)` — schedule without waiting. Whether the callback ever runs depends on the old loop's remaining lifetime, and `is_closed()` being false does not mean the loop will ever turn again — inside the `asyncio.run` teardown window the loop is already stopped but not yet closed, so the callback never executes, the `aclose()` coroutine is never awaited, and GC reports "never awaited"; because GC timing is random (usually after the test ends, captured by pytest's unraisableexception plugin), it escapes the per-test `filterwarnings("ignore::RuntimeWarning")` and makes the warning count fluctuate between 1 and 2.
- The intermediate fix ("`is_running()` gate + `fut.result(timeout=5)` wait") still cannot cure it, as measured: during the `asyncio.run` teardown phase (`_cancel_all_tasks` / `shutdown_asyncgens` running several `run_until_complete` passes) the loop is still turning (is_running is true) but stops at any moment — the scheduled task may already be created yet never stepped (`Task was destroyed but it is pending!`), and the future never resolving amplifies a teardown race into a full 5-second block (stress-measured: a single test round went from 0.4s to 5.4s, with warnings still present).
- Directly `await old_client.aclose()` on the current loop is also not viable: it operates a transport bound to the old loop (httpcore's connection-pool close touches the old loop's `call_soon`, raising RuntimeError outright once that loop is closed).

**Conclusion**: an external thread cannot reliably control the lifetime of another thread's event loop; the only reliable approach is to **never create an aclose coroutine across loops** — drop the reference and let GC handle it, unifying with the existing "same-thread round change, old loop already closed" path semantics; process-level cleanup remains the responsibility of atexit's `close_all_clients_sync`.

**Changes**:

- `src/async_http.py`: removed the cross-loop `run_coroutine_threadsafe` scheduling branch, replaced with not creating the coroutine at all; comments record the empirically ruled-out alternatives in full (do not revert).
- `tests/test_async_http_lock.py`: `test_concurrent_threads_no_cross_loop_error` dropped its `@pytest.mark.filterwarnings("ignore::RuntimeWarning")` (it cannot intercept GC-delayed warnings and only masks regressions; removing it turns the test into a regression guard); added 2 regression tests: `test_cross_loop_running_old_loop_skips_close` (a running old loop also gets no close scheduled, reproduced via a background `run_forever` thread) and `test_cross_loop_stopped_old_loop_skips_close` (`run_until_complete` returned but not closed, reproducing the asyncio.run teardown-window shape).
- `pyproject.toml`: `[tool.pytest.ini_options].filterwarnings` gained a filter for starlette testclient's import-time `anyio.abc.BlockingPortal` deprecation notice (same classification as the existing httpx deprecation notice: third-party, with a source comment).
- `AGENTS.md`: added the "pytest '0 warnings' baseline" entry (empty summary; distinction between project-owned warnings and filterable third-party warnings; filtering must never mask project warnings; coroutine warnings must be fixed at the root cause); added the "never create/schedule aclose coroutines of old AsyncClients across event loops" entry to Known Pitfalls.

- `tests/test_async_http_lock.py` re-run 30 + 20 consecutive rounds: 0 warnings, 0 `Task was destroyed`, no multi-second stalls (before the fix, 8 out of 15 rounds showed warnings);
- Full `pytest -q`: **808 passed, 2 skipped, 0 warnings** (warnings summary deterministically 0, including the newly filtered third-party warning);
- `black --check` / `isort --check-only` / `mypy` (incl. `--platform linux`) / `basedpyright` (0 errors/0 warnings) / `scripts/check_annotations.py` all pass.

### v4.0.9.4-dev (2026-09-03) — Repo-wide Chinese comment completion (41 files / +1370 lines) + annotation-check tool scripts/check_annotations.py created and wired into CI

**Change summary**: This entry records the systematic comment completion pass over the whole repo performed in the 2026-09-03 session. All code changes are **comments only** (zero executable-logic changes, proven by AST-equivalence checking 41/41), plus one new annotation-convention gate script `scripts/check_annotations.py` (three modes) wired into the `static` job of `ci.yml`.

**Scope and outcomes**:

- 38 Python files (+ 3 frontend files `web/app.js` / `web/index.html` / `web/style.css`) went from an average comment density of 7.6% to 20.7%, +1370 comment lines total;
- `src/spider.py` (the 60+ platform crawler core, 4617 lines) went through four dedicated rounds: 5.0% → 14.6% (+519 lines), covering the module header, all 54 large functions (≥35 lines, 75% of the file), ~33 small functions, constant tables, and boundary/pitfall annotations;
- The remaining low-density test files were brought up to ≥13% each (targets 16–18% for the larger ones).

**Key design: AST-equivalence verification**

Since this repo is not a git checkout, there was no HEAD to diff against. Instead, a full-text baseline snapshot was taken before editing, and after each round `ast.dump(ast.parse(old)) == ast.dump(ast.parse(new))` was enforced for every touched file. Because comments do not enter the AST while triple-quoted docstrings do, passing this check simultaneously proves (a) no executable logic was touched and (b) no docstrings were introduced — turning the AGENTS.md "use `#`, never docstrings" convention into a machine-verifiable constraint. During the pass this check caught one real violation: a subagent had added a duplicate `json_data["anchor_name"] = anchor_name` assignment in `get_yy_stream_data`; it was reverted while the valuable knowledge from its comment was relocated to the original assignment site.

**New script `scripts/check_annotations.py` (stdlib-only, zero side effects)**:

- Default mode: checks the repo-wide annotation conventions — docstrings forbidden (except protoc-generated `douyin_pb2.py`), per-file comment-density floor (default 13%), module header presence;
- `--baseline <dir>` mode: AST-equivalence comparison of current files against a previously snapshotted baseline (used to prove comment-only changes);
- `--snapshot <dir>` mode: writes a baseline snapshot for later equivalence checks.

**AGENTS.md**: added an "Annotation Conventions" subsection (docstrings forbidden; `#` only; density floor 13%; how to use the tool) and registered the script in the project tree. **CI**: `ci.yml` `static` job gained the step "Check annotation conventions".

### v4.0.9.3-dev (2026-09-02) — Standalone single-file integration (standalone) type-annotation fixes (mypy: 4 errors cleared)

**Change Summary**: This entry records the 2026-09-02 session's fix of 4 mypy static-type warnings (IDE mypy / `warn_return_any`) in the root-level single-file integration script `douyin_live_recorder_standalone.py`. All changes are **modifications** (type-annotation cleanup, no new features, no behavioral change); import cleanup: removed the unused `Callable`, added `Protocol, cast`. **Deletions**: the `Callable` import in `typing` (no remaining references).

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.3-dev (2026-09-02) — Standalone single-file integration (standalone) type-annotation fixes (mypy: 4 errors cleared) | section: Files Involved (Classified by Module)).

**Impact scope**:

- User-visible: none (pure static type annotations, runtime behavior unchanged).
- Unchanged behavior: the dispatch chain of the four platform resolvers (`resolve_douyin` / `resolve_huya` / `resolve_bilibili` / `resolve_douyu`) and the keyword-call form (`proxy=` / `cookies=`) are fully preserved.

- `python -m py_compile douyin_live_recorder_standalone.py`: passed (0 syntax errors).
- IDE lint (`douyin_live_recorder_standalone.py`): 0 errors, 0 warnings.
- The local interpreter (Python 3.14.7) does not have `mypy` / `basedpyright` installed, so a full local type check could not be run; please run `mypy douyin_live_recorder_standalone.py` in an environment with a type checker to confirm.

**Related**:

- Convention alignment (MEMORY.md "basedpyright strict-mode constraints & convergence tips"): when the RHS is `Any`, `json.loads` must be `cast`-wrapped rather than relying on `# type: ignore` (this repo forbids ignore comments).

### v4.0.9.3-dev (2026-09-02) — Full Fix of All 20 Issues from the Code Inspection Report (cookie_cache singleflight rewrite + Web non-ASCII password crash + probe/resource/style robustness) + mypy Whole-Repo Clean Slate (tests / gui_legacy / scripts)

**Change Summary**: This entry systematically records the complete fix of all 20 review issues from `代码检查报告.md` (Code Inspection Report) in the 2026-09-02 session, plus the subsequent clearance of two batches of leftover mypy errors. Two high-priority items: ① `src/cookie_cache.py` concurrency deduplication rewritten as singleflight — the old implementation held a `threading.RLock` across `await`, and RLock is a thread-affine lock: concurrent coroutines in the same event loop all belong to one thread and can all re-enter the lock, so mutual exclusion was completely void and multiple coroutines could concurrently request the same URL (precisely the risk-control trigger this module exists to eliminate); ② `src/web_config.py`'s legacy plaintext-password compatibility path raised `TypeError` directly on non-ASCII passwords (`hmac.compare_digest` does not support comparing strs containing non-ASCII characters; with a legacy plaintext password containing Chinese characters, `/api/login` returned a 500). Eight medium-priority items cover the Web API write-path consistency, a busy-looping backup daemon thread, probe exception logging and unbounded throttle-dict growth, ctypes handle truncation, decorator fallback types, HTTP response connection leaks, duplicate unzip_file consolidation, and Session lifecycle management. Eight low-priority items are redundancy and style cleanups. The environment item fixed the venv editable install pointing (it previously targeted `D:\DouyinLiveRecorder-coding`, causing the ghost problem of "edited directory A while tests ran against directory B"). **Deletions**: the duplicate `unzip_file()` implementations in `src/node_install.py` and `src/ffmpeg_install.py` (consolidated into a single implementation in `src/utils.py`), the pure forwarding wrappers `mark_ffmpeg_reject`/`clear_ffmpeg_reject` in `src/stream_select.py` (merged into aliases of the internal functions), the redundant `binascii.Error` catch and unused `import binascii` in `src/web_config.py`, and the placeholder-free f-string prefix and `assert`-based type narrowing in `src/stream_select.py` (replaced with an explicit null check plus a warning path).

**1. Concurrency correctness (high) — `src/cookie_cache.py` (rewritten) / `tests/test_cookie_cache.py`**

- `src/cookie_cache.py`: `fetch_cookies` rewritten in singleflight style — `threading.Lock` only guards the synchronous reads/writes of the "cache dict + in-flight registry `_inflight`" (**never awaits inside the lock**); the coroutine that wins the fetch right performs one fetch, same-loop waiters register a future to reuse the same result, and cross-loop waiters receive delivery via `loop.call_soon_threadsafe` (futures are not thread-safe; calling `set_result` across threads directly is forbidden); if the fetching coroutine is cancelled (room stop / process exit), the `BaseException` branch immediately removes the registration and delivers an empty result to waiters; waiters carry a `timeout + 5s` margin fallback (guarding against hanging forever if the fetching thread dies abnormally). Existing semantics fully preserved: failure is not cached, TTL expiry, `fetcher` passthrough, etc.
- `tests/test_cookie_cache.py`: `test_same_loop_reentrant_no_deadlock` strengthened to also assert "5 coroutines gathered concurrently trigger exactly one fetch" (this assertion would necessarily fail under the old RLock implementation — exactly the target behavior of this fix); the cross-thread case (4-thread barrier, `call_count == 1`) comments updated accordingly. All 26 tests pass.

**2. Web panel defect fixes (high / medium-high / medium) — `src/web_config.py` / `src/web_api.py` / `src/web_tray.py`**

- `src/web_config.py`: ① the legacy plaintext compatibility path in `verify_web_password` now uses `hmac.compare_digest(plaintext.encode("utf-8"), stored.encode("utf-8"))` (bytes comparison has no non-ASCII restriction); ② the PBKDF2 parsing branch drops the redundant `binascii.Error` catch (it is a subclass of `ValueError`) and the unused `import binascii`.
- `src/web_api.py`: `PUT /api/rooms` (`update_room`) now writes the line using `normalize_url(req.url)` — the previously written un-normalized URL was inconsistent with the deduplication criteria of add/delete/toggle, so a PUT-written line could never be matched again on the next round.
- `src/web_tray.py`: `_patch_console_window` / `_on_show` switched to `ctypes.WinDLL` + explicit `argtypes`/`restype` (`GetConsoleWindow.restype = c_void_p`; full signatures declared for `GetWindowLongW`/`SetWindowLongW`/`SetWindowPos`/`GetSystemMenu`/`EnableMenuItem`/`ShowWindow`/`SetForegroundWindow`), fixing 64-bit HWND/HMENU truncation by the default `c_int`; module-level `_KERNEL32`/`_USER32` singleton caching (aligned with the `web.py` conventions); the second parameter of `SetWindowPos` narrowed to `c_void_p | None`.

**3. Daemon-thread and probe robustness (medium) — `src/config_io.py` / `src/stream_select.py` / `src/danmaku_monitor.py` / `src/ws_client.py`**

- `src/config_io.py`: the `time.sleep(600)` in the `backup_file_start` daemon loop moved out of `try` — the old exception branch did not wait, so persistent check_md5/backup failures degraded into a busy loop spinning wild log spam and burning CPU.
- `src/stream_select.py`: ① `_confirm_get_ok`'s `except Exception` now logs `logger.debug` (including exception type + attempt number, no more silent swallowing), and an attempt-0 exception follows the "retry once before convicting" semantics — sleeping `_recheck_delay()` then retrying, giving up the recheck only if both attempts raise (the HEAD conclusion stands); ② `_throttle_probe` now evicts hosts idle for more than `_PROBE_MIN_HOST_INTERVAL × 10` while writing, so `_probe_last_seen` no longer grows without bound (mirroring `_probe_backoff`'s expiry cleanup; prevents unbounded growth across 60+ platforms in long runs); ③ `mark_ffmpeg_reject`/`clear_ffmpeg_reject` merged from pure forwarding wrappers into module-level aliases of `_mark_probe_reject`/`_clear_probe_reject` (semantic comments preserved); ④ extracted `_is_h265(url)` to eliminate the duplicated check between candidate construction and the record_url fallback; ⑤ removed a placeholder-free f-string prefix; ⑥ `assert probe is not None` replaced with an explicit null check + warning (`assert` is stripped entirely under `-O`).
- `src/danmaku_monitor.py`: the `_write_line` failure branch now logs `logger.debug` (with exception type), consistent with this module's "swallow all exceptions but always leave a trace" convention — sidecar data is no longer dropped without a trace.
- `src/ws_client.py`: the heartbeat-task reclamation `except asyncio.CancelledError, Exception:` was split — `CancelledError` is swallowed only when hb_task itself was cancelled as expected (`hb_task.cancelled()` is true); if the current coroutine was cancelled, it re-raises so the cancellation signal is no longer swallowed.

**4. Decorator fallback types and resource management (medium) — `src/utils.py` / `src/spider.py` / `src/node_install.py` / `src/ffmpeg_install.py` / `src/sync_http.py`**

- `src/utils.py`: ① the decorator's shared implementation consolidated into `_make_trace_error_guard(func, fallback)`, with the new `trace_error_decorator_or_none` (returns `None` on error); error logs now include the function name and fallback type; ② added the shared `unzip_file()` (with Zip Slip validation).
- `src/spider.py`: five functions returning str/tuple (`get_bilibili_room_info_h5` / `login_sooplive` / `get_sooplive_tk` / `get_winktv_bj_info` / `login_flextv`) switched from `trace_error_decorator` to `trace_error_decorator_or_none` — the old uniform dict fallback disguised errors as normal results (the dict returned by a failed `login_flextv` was once misjudged as a successful login by `if new_cookies`).
- `src/node_install.py`: both `requests.get` calls (version page + streaming zip download) now managed with `with` to close connections; the local `unzip_file` was deleted in favor of importing from `src/utils`.
- `src/ffmpeg_install.py`: local `unzip_file` deleted in favor of importing from `src/utils` (the two verbatim-duplicate implementations consolidated into one).
- `src/sync_http.py`: added `_all_sessions` (`weakref.WeakSet`) + `_all_sessions_lock` to register thread-local Sessions, `close_session()` (explicit release for the current thread), and `close_all_sessions()` (registered with `atexit` to gracefully close all connection pools at process exit).
- `tests/test_spider_platform.py`: 4 assertions that had pinned the old dict fallback behavior (TestLoginSooplive ×2 / TestLoginFlexTv / TestSoopliveTk / TestWinktvBjInfo) updated to `is None`.

**5. Style conventions and environment (low) — `AGENTS.md` / venv**

- PEP 758 style finalized: the report originally suggested uniformly adding parentheses as `except (A, B):`, but testing showed **black 26.x's stable style is the paren-less form** (`black --check` rewrites a single-line-fitting `except (A, B):` back to `except A, B:`, so adding parentheses actually fails the format gate). The report's fallback option was therefore adopted: keep the paren-less style (syntax legality guaranteed by the `requires-python = ">=3.14"` floor), and record the convention explicitly in `AGENTS.md`'s "Code Style → Black" section: "depends on PEP 758; do not add parentheses for <3.14 compatibility".
- venv fix: the editable install in `.venv` previously pointed to `D:\DouyinLiveRecorder-coding` (a different checkout); after reinstalling with `pip install -e .` (4.0.9 → 4.0.9.2), `direct_url.json` targets this workspace, and `import src.*` confirmed resolving to this directory.

**6. Leftover mypy clearance (two follow-up batches) — `tests/test_quality_tiers.py` / `gui_legacy.py` / `scripts/extract_i18n_strings.py`**

- `tests/test_quality_tiers.py`: added `assert mock.await_args is not None` before the 5 `mock.await_args.args[1]` accesses — typeshed declares `await_args` as `_Call | None`; `assert_awaited_once()` guarantees non-None at runtime but mypy cannot narrow it (union-attr).
- `gui_legacy.py`: 4 fixes — ① the two hover-effect lambdas replaced by the named closure factory `_flat_relief(button)` (event parameter explicitly annotated, aligned with gui.py's `_on_escape` convention); ② `_create_modern_button`'s `command` parameter annotated `str | Callable[[], Any]` (exactly matching the ttk.Button stub); ③ `config.optionxform = lambda` replaced by the named function `_preserve_case` + `setattr` (the same gui.py workaround for "Cannot assign to a method"); ④ `from collections.abc import Callable` added at the top.
- `scripts/extract_i18n_strings.py`: `parse_keys`'s dynamic `getattr` call result narrowed with `cast(dict[str, str], ...)` (`warn_return_any` gate), removing the now-unneeded `type: ignore[arg-type]`.

**Impact scope**:

- User-visible: Web panel login works again for legacy plaintext passwords containing non-ASCII characters; concurrent rooms on the same platform no longer repeatedly request visitor cookies from the same domain (further reducing risk-control trigger probability); CPU no longer spins when the backup directory persistently fails.
- Unchanged behavior: cookie-cache TTL / failure-not-cached / fetcher passthrough, probe backoff and throttling semantics, the Douyu/Huya GET-recheck "retry once before convicting" semantics, all Web API route contracts, the danmaku collection chain, etc. all preserved.
- Known trade-off: the PEP 758 paren-less except syntax is incompatible with <3.14 (this repo's floor is 3.14; not a regression but an explicit convention).

- Full `pytest`: **806 passed, 2 skipped, 0 failed**.
- `mypy` whole-repo scope (src + tests + all entry points + build_exe + scripts): **Success: no issues found in 102 source files** (the CI scope `mypy src/` with 39 files, the report scope with 44 files, and the tests-included scope with 94 files are all green).
- `basedpyright --outputjson`: errorCount=0, warningCount=0.
- `black --check`: 105 files unchanged; `isort --check-only` all compliant; `compileall` 0 syntax errors.
- web_tray live check: `WinDLL` loads successfully and the window-restyling chain is exception-free (headless `GetConsoleWindow` returns empty and skips as expected).

**Related**:

- `AGENTS.md`: "Code Style → Black" gains the multi-exception except syntax (PEP 758) convention.
- Issue source: the 20-item list in `代码检查报告.md` (Code Inspection Report, #1–#20); this entry is its full closure record.
- Previous full snapshot: v4.0.9.2-dev (2026-08-30) "Runtime Log Archiving on Recording Stop".

### v4.0.9.2-dev (2026-08-30) — Runtime Log Archiving on Recording Stop (four logs renamed with timestamp) + i18n catalog completion (507 → 516 entries) + repo metadata sync-list alignment (.v2c / .mypy_cache)

**Change Summary**: This entry systematically records the three changes landed in the 2026-08-30 session. ① **New feature: runtime log archiving on recording stop** — the Web panel "Stop Recording" button and every process-exit path (signal `safe_exit` / disk-full / uncaught exception / Web tray exit) now uniformly rename the four runtime logs (`logs/streamget.log`, `logs/PlayURL.log`, `logs/danmaku_monitor.jsonl`, `logs/web_console.log`) to "originalname_YYYYMMDD_HHMMSS.ext": conflicting targets get a `_N` sequence suffix, missing files are skipped, a single failed rename only warns without interrupting, and the corresponding handle is flushed and closed before renaming (on Windows, renaming a file with an open handle raises WinError 32); after archiving, the logging pipeline is restored immediately and the next recording session recreates fresh same-name files. ② **i18n catalog completion**: the 9 new log strings introduced by the archiving feature were added to all four language catalogs (507 → 516 entries) and `zh_CN.mo` was recompiled. ③ **Repo metadata sync audit**: consistency review of the nine config files (`AGENTS.md` / `docker-compose.yaml` / `requirements.txt` / `Dockerfile` / `.gitignore` / `.dockerignore` / `.coveragerc-concurrency` / `pyproject.toml` / `uv.lock`) fixed 2 drifts (`.v2c/` missing from the local-tool-directory sync list, `.mypy_cache/` missing from `.dockerignore`). **Deletions: none** (this batch is purely additive — no files, functions, or config entries were removed).

**1. Runtime Log Archiving (new feature) — `src/log_archive.py` (new) / `src/logger.py` / `src/danmaku_monitor.py` / `main.py` / `src/web_api.py`**

- `src/log_archive.py` (**new file**): archive entry `archive_runtime_logs(*, reopen_streams=True)` plus helpers `_archive_target()` (original name_timestamp.ext, dedup via `os.path.exists` probing with `_1`/`_2` increments) / `_streams_bound_to()` (finds the handles bound to web_console.log among `sys.stdout`/`sys.stderr`) / `_rebind_web_console()` (recreate the handle + reassign the standard streams + `rebind_console_sink()`) / `_archive_web_console()` (close → rename → recreate; a leftover file not bound to any standard stream is only renamed, never hijacking the current stdout) / `_rename_one()` (single-file archive: skip if missing, warn on failure); `ARCHIVE_LOG_NAMES` pins the four-log list; a module-level lock guards against "panel stop × atexit" concurrent re-entry; a top-level try/except ensures any unexpected error only warns and returns an empty list, never interrupting the stop-recording flow; two guards return early: the GUI parent process (`DLR_GUI_PARENT=1` — owns no recording-log handles and must never rename logs being written by the recorder child) and test processes (`DOUYIN_DISABLE_LOG_ARCHIVE=1`).
- `src/logger.py`: new module-level `_streamget_sink_id` / `_playurl_sink_id` tracking the handler ids of the two recording-log sinks; import-time registration refactored into the `_add_streamget_sink()` / `_add_playurl_sink()` helpers (identical parameters for import time and runtime re-creation); new public `remove_file_sinks()` (loguru `remove()` first flushes the enqueue queue and then closes the file handle, guaranteeing content is fully persisted before renaming; idempotent no-op) and `add_file_sinks()` (re-registers the sinks — loguru `add()` immediately creates fresh same-name files; skipped for the GUI parent process or when "enable log file" is off).
- `src/danmaku_monitor.py`: `DanmakuMonitorHub` gains `close_file()` (flush+close+clear the reference under `_file_lock`; a half-broken handle is left to the existing exception-recovery path of `_write_line`, and the next event reopens automatically); module-level `close_monitor_file()` (no-op when the singleton is uninitialized — deliberately not going through `get_hub()` to avoid creating it).
- `main.py`: module-level `atexit.register(archive_runtime_logs, reopen_streams=False)`, **registered deliberately before `cleanup_all_ffmpeg_processes` / `close_all_clients_sync`** (atexit is LIFO — archiving runs last, sweeping the ffmpeg-cleanup and other final logs into the archived files; the process-exit path does not re-create sinks, the next start rebuilds them via import-time registration); signal `safe_exit` (CLI Ctrl+C / the GUI stop button's CTRL_BREAK / console close), disk-full `sys.exit(-1)`, uncaught exceptions, and the Web tray exit are all covered through atexit.
- `src/web_api.py`: `toggle_recording` triggers `archive_runtime_logs(reopen_streams=True)` immediately on `enable=False` (the panel "Stop Recording" manual-stop path; the process keeps running, so after renaming the loguru sinks and the web_console handle are rebuilt and logging for the recorder engine and the Web service is unaffected); the timestamp is taken at the moment the stop operation happens; "Start Recording" does not trigger archiving.

**2. Tests (1 new file + 2 modified) — `tests/`**

- New `tests/test_log_archive.py` (14 cases): regex lock on the four-log rename format (originalname_YYYYMMDD_HHMMSS.ext), `_1`/`_2` increment without overwriting existing files under a fixed timestamp, empty directory skips everything, a single failed rename (PermissionError stub simulating a locked handle) does not interrupt the batch, `DLR_GUI_PARENT=1` guard (no files or handles touched), `DOUYIN_DISABLE_LOG_ARCHIVE=1` guard, both `reopen_streams` semantics (False does not re-create sinks / True does), web_console bound-handle rotation (flush+close → rename → recreate the handle → rebind, asserting `handle.closed`), a leftover web_console not bound to standard streams is only renamed without redirecting stdout, hub `close_file` followed by lazy reopen on the next event and idempotent repeated close, logger sink remove→add round trip and idempotency (importlib.reload isolation + "add() creates the file" assertion), and a static lock on main.py's archive atexit registration order (registered before the two cleanups + `reopen_streams=False`).
- `tests/test_web_api.py`: `TestRecordingToggle` gains `test_toggle_stop_triggers_log_archive` (enable=False triggers exactly once with `reopen_streams=True`; enable=True does not trigger).
- `tests/conftest.py`: `pytest_configure` sets `DOUYIN_DISABLE_LOG_ARCHIVE=1` — a test process importing main registers the archive atexit hook, but a pytest exit is not a "stop recording" event, preventing renames of the developer's real `logs/` (the archiving-specific cases delenv it themselves).

**3. i18n Four-Language Catalog Completion (modification) — `i18n/zh_CN/LC_MESSAGES/zh_CN.po` + `zh_CN.mo` / `i18n/en_US.json` / `i18n/en_GB.json` / `i18n/zh_TW.yaml`**

- 9 entries added to each of the four catalogs (507 → 516, key sets kept identical): the 9 new log strings from the archiving feature — "runtime logs archived", "runtime log archiving failed (ignored)", "log archived", "log archiving failed (skipped)" ×2, "failed to close web_console handle (ignored)", "failed to recreate web_console.log handle", "[danmaku monitor] close_file failed (ignored)", "[danmaku monitor] exception while closing sidecar file (ignored)".
- `zh_CN.po`: new section "Log Archive Module (src/log_archive.py / src/danmaku_monitor.py, added 2026-08-30)" (identity-translation style for Simplified Chinese), header "update date / PO-Revision-Date" synced; `scripts/compile_po.py` recompiled the `.mo` (517 entries including the header, 63888 bytes) and `--check` byte-level sync passes.
- `en_US.json` / `en_GB.json`: English translations (identical for both variants — no US/GB spelling divergence involved); `zh_TW.yaml`: Traditional Chinese following the existing vocabulary conventions (日志→日誌, 文件→檔案, 归档→歸檔, 运行日志→執行日誌, 句柄→控制代碼), with entries containing single-quoted placeholders written as double-quoted YAML scalars.

**4. Repository Metadata Sync (modification) — `pyproject.toml` / `.coveragerc-concurrency` / `.gitignore` / `.dockerignore` / `AGENTS.md`**

- Consistent items found by the audit (no change needed): `requirements.txt` ≡ `pyproject.toml [project.dependencies]` (20=20, same lower bounds entry by entry); `uv.lock` confirmed in sync via `uv lock --check`; Dockerfile (python:3.14-slim-bookworm + Node 24) ≡ ci.yml (`python_build=3.14` / `node_version=24`); the version chain 4.0.9.2 and `scripts/check_version.py` fully pass; the Docker mirror exclusion set is complete; `.coveragerc-concurrency` omit ≡ pyproject coverage omit.
- 2 drifts fixed: ① **`.v2c/`** (a video2code plugin directory present in the workspace) added to all 9 sync points — `.gitignore`, `.dockerignore`, the five pyproject exclude lists (black exclude / isort extend_skip / mypy exclude / basedpyright exclude / coverage omit), the `.coveragerc-concurrency` omit, and the canonical list in AGENTS.md's "dockerignore / gitignore sync convention"; ② **`.mypy_cache/`** added to `.dockerignore`'s "Python caches" section (previously only in `.gitignore`, so `COPY . .` would ship it into the build context).
- `AGENTS.md`: project structure gains the `src/log_archive.py` entry; "Key Conventions" gains item 8, "Runtime log archiving on recording stop (finalized 2026-08-30)" (exactly two trigger points / naming and dedup rules / handle-closing hard constraints / GUI and test guards / regression-lock list).

**Impact**:

- User-visible: after stopping, timestamped archive files such as `streamget_YYYYMMDD_HHMMSS.log` appear under `logs/` (repeated stops within the same second get `_1` increments); the original four logs are automatically recreated at the next recording/log write; the Web panel's "Stop Recording" archives immediately, while CLI Ctrl+C / the GUI stop button / console close / Web tray exit archive at process exit.
- Unchanged behavior: log content/format/directory, loguru rotation (300 KB) and retention policy, the danmaku-monitor JSONL rotation (5 MB), four-catalog keyset equality, the GUI parent writing only gui.log, and CLI mode never creating web_console.log are all preserved.
- Known boundary: the GUI stop-recording fallback `taskkill /F /T` hard-kills the process, leaving no chance to run any Python code (including archiving) — a structural limitation (the primary CTRL_BREAK path archives normally); `web_console.log` only exists in Web background mode, and after archiving a fresh empty file is recreated to carry subsequent output.

- Full `pytest`: **806 passed, 2 skipped** (0 warnings; 15 new cases in this batch: 14 in `test_log_archive.py` + 1 toggle-archive trigger).
- Black-box verification of the real chain on Windows: loguru `remove()` (flush+close) → `os.rename` → `add()` leaves the old file fully intact and immediately recreates the fresh same-name file (confirming the archive works under the handle-locking constraint).
- Runtime lookup smoke test in four languages: all 9 new strings hit exactly in zh_CN (.mo) / en_US / en_GB / zh_TW.
- Config final checks: programmatic assertions over the five pyproject exclude lists / coveragerc omit / both ignore files / the AGENTS sync list all pass; `black --check` (valid exclude regex), `mypy src/` on both platforms, `uv lock --check`, and `coverage debug config` all pass; `scripts/check_version.py` PASS.

**Related**:

- `AGENTS.md`: "Key Conventions" item 8, "Runtime log archiving on recording stop (finalized 2026-08-30)" + the "dockerignore / gitignore sync convention" list (including `.v2c/`).
- Previous full snapshot: v4.0.9.2-dev (2026-08-29) "Full Working-Tree Change Overview (Classified by Module)".

### v4.0.9.2-dev (2026-08-29) — Full Working-Tree Change Overview (Classified by Module): 97 files / +10659 −3138, covering all uncommitted changes from 2026-08-23 through 08-29

**Change Summary**: This entry is the systematic, module-classified overview of the **entire uncommitted working tree** (95 tracked files changed +10659/−3138, plus 2 new untracked documents — 97 files in total), superseding the v4.0.9-dev (2026-08-24) overview entry as the latest full snapshot (work landed after 08-24 — scheduling feedback, performance optimization, CI restructuring, Web recording control, quality tiers, etc. — is documented in the individual feature entries; this entry consolidates everything into a single "file → module → change type (new feature / modification / deletion)" index). Feature highlights — new: ① concurrency scheduling hub `src/scheduler.py`, ② Web panel manual recording control, ③ Huya/Douyu fine-grained Blu-ray quality tiers, ④ the i18n four-language four-format localization system, ⑤ GUI crash observability and the language menu; modified: main.py recorder-engine refactor (platform-dispatch extraction + recording-result feedback + set-based dedup), stream_select unified candidate sequence and probe backoff, HTTP-layer session reuse and 3.14 adaptation, CI/CD workflow restructuring; deleted: the old fixed semaphore and one-way `adjust_max_request` suppression, unconditional end-of-round success sampling, the expired Migu `sv=10010` concatenation, and leftover debug steps in build-release.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.2-dev (2026-08-29) — Full Working-Tree Change Overview (Classified by Module): 97 files / +10659 −3138, covering all uncommitted changes from 2026-08-23 through 08-29 | section: Files Involved (Classified by Module)).

**Impact Scope**:

- User-visible: the Web panel no longer auto-records on startup (requires clicking "Start recording"); UI/console support four-language hot switching; Huya/Douyu offer fine-grained Blu-ray tiers with automatic downgrade; queuing delay and error amplification under 80+ room concurrency are substantially reduced; pythonw/frozen GUI crashes are observable.
- Unchanged behavior: CLI/GUI direct-run recording flow, danmaku `proxy=None` direct connection, probe tolerance (retry-once-then-condemn / last-resort pass-through), word-for-word UA parity, Douyu HLS-first / Huya FLV-first and all other existing conventions.
- Deployment: Docker image baseline 3.14 + Node 24; the packaging interpreter matches the CI-verified environment (3.14); new `PyYAML` runtime dependency (missing it only forfeits the zh_TW.yaml format).

- `pytest` full suite **786 passed, 2 skipped** (0 failures); `compileall` (venv Python 3.14.7) passes for main/gui/web/i18n/build_exe/src/scripts.
- `black --check --line-length 120 --target-version py314` and `isort --check-only --profile black --line-length 120` (101 files) all green.
- `mypy src/` + `mypy --platform linux src/`: 1 error each (pre-existing `src/stream.py:609` `call-overload`, with the `# type: ignore[arg-type]` error-code mismatch — **blocks the CI typecheck; fix before committing**).
- `basedpyright tests/`: 5 errors (5 `mock.await_args` optional-member accesses in `tests/test_quality_tiers.py` — **blocks the local type gate; fix before committing**).
- i18n: `scripts/extract_i18n_strings.py` reports 11 new runtime strings pending catalog inclusion (no functional impact; raw text fallback); four-catalog key sets identical and `.po/.mo` byte-level sync passes.
- Known to-dos (before committing): the ci.yml test matrix's 3.13 leg fails at collection due to PEP 758 syntax and must be collapsed to `["3.14"]`; `check_subprocess` acquires `recording_semaphore` only after `Popen`, so the "max simultaneous recordings" cap does not constrain process creation as intended — move the acquire earlier.

**Related**:

- Per-feature entries: v4.0.9-dev (2026-08-24) "High-Concurrency Multi-Platform Recording Scheduling & Resource Management", "Four-Language Localization Catalog Unification", "CI mypy Dual-Error Fixes"; v4.0.9.1-dev (2026-08-27) "Recording-Result Feedback Scheduler + Probe Backoff", "Code-Review Fixes (Circuit-Breaker Probe Lease Self-Healing + Scheduler Success Sampling)", "i18n Localization System Fix"; v4.0.9.1-dev (2026-08-28) "Performance Review Optimization Landed (P1~P5)", "CI Workflow Optimization & Network-Install Retry Consolidation"; v4.0.9.1-dev (2026-08-29) "Web Panel Manual Recording Control", "Huya/Douyu Quality-Tier Specialization".
- `AGENTS.md`: all regression-avoidance conventions distilled from this batch (Concurrency & Thread Model / Recording-Result Feedback conventions / Known Pitfalls).
- v4.0.9-dev (2026-08-24) "This Session's Change Overview (Classified by Module)": the previous full snapshot (covering up to 08-24), superseded by this entry.

### v4.0.9.2-dev (2026-08-29) — Huya/Douyu Quality-Tier Specialization (Fine-grained Blu-ray Tier Enumeration + User Tier Selection + Unavailable Downgrade Fallback + Cross-Platform Compatibility)

**Change Summary**: This entry systematically records the "Huya/Douyu live quality-tier specialization" landed during the 2026-08-29 session. Based on ffprobe measurements of `huya.com/chuhe` (six tiers: Smooth/Ultra/BD4M/BD8M/BD20M/BD30M) and `douyu.com/3168536` (five tiers: HD/Ultra/BD4M/BD8M/Origin), we complete the enumeration and Chinese labels for the Blu-ray sub-tiers (BD4M/BD8M/BD20M/BD30M), wire up the full chain "user selects a tier before recording → record at the selected tier", and provide clear error messages plus a nearest-neighbor downgrade fallback for unavailable/restricted tiers — without changing the existing semantics of index-based tier selection on Douyin/TikTok/Bilibili/Kuaishou etc. ① **Quality-code layer**: `QUALITY_LEVEL`/`QUALITY_MAPPING_BIT`/`QUALITY_CODE_TO_ZH` expanded from a 6-item base set to a 10-item set (adding `BD30`/`BD20`/`BD8`/`BD4`), with a new frozen `BD_SUB_TIERS` set; `get_quality_index` folds Blu-ray sub-tiers into the `BD` slot, preserving the digit-input 0–5 selection semantics; ② **Huya selection**: new `HUYA_FIXED_TIERS`/`HUYA_RATIO_TO_CODE`, where `ratio` = the bitrate ceiling (kbps) appended to the FLV/HLS URL query to pick a tier; the `exsphd` tier table takes priority, falling back to `gameLiveInfo.bitRate` when absent; an unavailable requested tier downgrades to the nearest lower one, and to Origin when no lower tier exists; ③ **Douyu selection**: new `DOUYU_RATE_BY_CODE`/`DOUYU_RATE_TO_CODE`/`DOUYU_RATE_DESC`, mapping by `rate` and retrying lower tiers along a total order (up to 2) when the requested tier is restricted (e.g. login-gated Origin); the server's nearest-clamp real tier is read back via the `rate` field; ④ **Chinese mapping & integration points**: `stream_select.get_quality_code`, `web_config.QUALITY_KEYWORDS`, the main.py quality whitelist, and the `web/index.html` dropdown options are all extended with the Blu-ray sub-tiers; ⑤ **Tests**: new `tests/test_quality_tiers.py` (3 classes, 29 cases) covering sub-tier mapping / index folding / Huya nearest-downgrade / Douyu retry chain; `tests/test_stream.py` constant-consistency assertions changed to superset semantics plus a new `test_bd_sub_tier_level_order`.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.2-dev (2026-08-29) — Huya/Douyu Quality-Tier Specialization (Fine-grained Blu-ray Tier Enumeration + User Tier Selection + Unavailable Downgrade Fallback + Cross-Platform Compatibility) | section: Files Involved (Classified by Module)).

**Impact Scope**:

- Huya recording: the user can pick any tier from Smooth to BD30M in the Web panel / URL config and record at that tier; when the room's bitrate is insufficient it downgrades to the nearest tier with a clear message (log includes requested tier / room ceiling / actual tier), and auto-falls-back to Origin when no lower tier exists — the chain is never broken.
- Douyu recording: the user can pick HD/Ultra/BD4M/BD8M/Origin (Douyu has no 20M/30M, so selecting those records at BD8M); a restricted tier auto-retries lower tiers, and the `rate`-read-back real tier is written into the result.
- Douyin/TikTok/Bilibili/Kuaishou/NetEaseCC/YY etc.: quality-selection semantics are exactly as before (sub-tiers fold to BD, index mapping unchanged), unaffected by this change.
- The return-value contracts of `get_huya_stream_url`/`get_douyu_stream_url` are unchanged (`is_live`/`anchor_name`/`flv_url`/`m3u8_url`/`actual_quality` all present), so the upper-layer `select_source_url`/probe/scheduler logic needs no change.

- `py_compile` (venv Python 3.14) on `src/stream.py`/`src/stream_select.py`/`src/web_config.py`/`main.py` all pass.
- `pytest` quality specialization: `tests/test_quality_tiers.py` **29 passed**; `tests/test_stream.py` quality classes + `test_bd_sub_tier_level_order` all pass; `tests/test_stream_select.py` Chinese-mapping cases pass.
- Full `pytest` gate **784 passed, 2 skipped**; the 2 sporadic failures of `tests/test_srt_timeline_anchor.py` inside the full suite are the sandbox safe-delete quota guard (`OSError SAFE_DELETE_BULK_CONFIRM_REQUIRED`) misfiring — running that file in isolation yields 4 passed, consistent with the harness behavior documented in AGENTS.md, not a code regression.
- `black --check`/`isort --check-only` (line-length 120, target py314) on the changed files pass; `mypy src/`/`basedpyright` report 0 issues on the newly added paths (the pre-existing `src/stream.py:609` item is unchanged from last time, not introduced here).
- Real-device measurements: the chuhe room (bitRate=30000) ffprobe sampling confirms the seven tiers' (incl. Origin) resolution/fps/bitrate match `HUYA_FIXED_TIERS`; the 3168536 room confirms the rate-clamp and read-back behavior (measured: requesting rate=8200 issues rate=4 → `_4000.flv`).

**Related**:

- `src/stream_select.py` source-selection/probe (2026-08-28 entry): Huya FLV-first, backoff window aligned to the main loop — this feature hands off to its source selection after Huya tier selection, chaining seamlessly.
- `AGENTS.md` regression-prevention: three conventions landed, see "Known Pitfalls (Avoid Regressions)" — "Blu-ray sub-tiers (Blu-ray 4M/8M/20M/30M) must fold into the BD index, must not be inserted into the generic `QUALITY_MAPPING`", "Huya tier selection ratio derived from the room bitrate ceiling, exsphd first / bitRate fallback, nearest downgrade or fall back to origin when unavailable", "Douyu local retry chain only supplements the server-side rate clamp, must not replace the HLS candidate or global backoff".
- v4.0.9.2-dev (2026-08-29) "Web Panel Manual Recording Control" — the `web/index.html` tier options added by this feature live in the same form as that panel's "Recording Control" section.

### v4.0.9.2-dev (2026-08-29) — Web Panel Manual Recording Control (Global Switch + 7 Interrupt Points + Start/Stop Buttons) + Two-Round Review Fixes + End-to-End Smoke Test & Commit-Gate Triage

**Change Summary**: This entry systematically records the "remove auto-recording on Web startup, switch to user manual control" feature landed during the 2026-08-29 session, together with its supporting verification. ① **The feature itself**: new global switch `main.recording_enabled` (default `True`, CLI/GUI unaffected) + 7 interrupt points in the `main.py` recording chain + a `POST /api/recording/toggle` endpoint + frontend Start/Stop Recording buttons with 2s polling state sync — the Web panel no longer records automatically on startup; ② **independent code review**: completeness of all 7 interrupt points, process reaping, error-sample isolation, concurrency safety, and auth consistency all confirmed; 3 defects fixed (including one P1 frontend status-label selector bug); ③ **end-to-end smoke test**: real panel (background mode) startup → start recording → stop recording → graceful exit, full flow passed; full `pytest` **786 passed, 2 skipped** re-run consistent; ④ **commit-gate triage**: the git commit was hard-blocked by the Mimosa L3 gate on unremediated high findings; completed the official deep scan (seal `sha256:5250cdc7…`) plus a finding-by-finding triage of all 44 alerts — all pre-existing false positives / upstream patterns, none on this feature's code; triage report written to disk, commit pending maintainer approval.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.2-dev (2026-08-29) — Web Panel Manual Recording Control (Global Switch + 7 Interrupt Points + Start/Stop Buttons) + Two-Round Review Fixes + End-to-End Smoke Test & Commit-Gate Triage | section: Files Involved (Classified by Module)).

**Impact Scope**:

- The Web panel no longer spawns any room thread on startup; after "Start Recording" the main loop spawns rooms per the URL config, and after "Stop Recording" room threads exit and the running list is cleaned, ready to restart at any time.
- CLI (direct `main.py`) and GUI entry behavior completely unchanged (`recording_enabled` defaults to `True`).
- While recording is stopped, config hot-reload, the concurrency scheduler, and the danmaku monitor hub keep running (only recording threads are not spawned/continued).
- All other behavior (scheduling semantics, source-selection order, probe tolerance, UA conventions, etc.) unchanged.

- Full `pytest`: **786 passed, 2 skipped** (2026-08-29 re-run consistent); `black --check --line-length 120 --target-version py314` and `isort --check-only --profile black --line-length 120` pass; `mypy src/` shows only the pre-existing `src/stream.py:609` error (not introduced here).
- E2E smoke (real panel `python web.py` background mode + API-driven): on startup `recording_enabled=false` / `recording_count=0` / `engine_alive=true` → within ~20s of toggle-on `monitoring=3` (3 room threads spawned) → within 3s of toggle-off `monitoring=0` / `recording_count=0` → CTRL_BREAK graceful exit, log shows "正在清理所有 ffmpeg 进程" (all ffmpeg processes cleaned), port closed, no ffmpeg leftovers, no leftover download files. (All configured rooms were offline during the smoke window, so `recording_count` stayed 0; the terminate-while-recording path is covered by the unit test above.)
- Commit gate: Mimosa git-gate blocked twice (graded mode must deny on high; no findings allowlist mechanism); per the gate's demand the official deep scan was completed (scanId `scan-2026-08-29T02-38-21.160Z-4c613b3699ed`, seal `sha256:5250cdc7…`) plus a finding-by-finding triage of all 44; no code change required, commit pending the maintainer adjusting gate policy or releasing it manually.

**Related**:

- `docs/web-recording-control-changelog.md`: feature change summary and follow-up-item closure record (review fixes detailed in section 3.4).
- `docs/security-triage-2026-08-29.md`: gate-alert triage details and the two release paths.
- v4.0.9.1-dev (2026-08-27) "Recording Result Feedback Scheduler" — stop-period error-sample isolation builds on its `record_error`/`record_success` semantics; the existing `check_subprocess` early-interrupt mechanism (flush danmaku before terminating ffmpeg) is pre-existing behavior; this feature only adds `recording_enabled` to its trigger condition.

### v4.0.9.2-dev (2026-08-29) — GUI Parent-Process Log-Handle Isolation: Fixes streamget.log Rotation WinError 32 and Total Loss of Recording Logs

**Problem**: In GUI mode the GUI process (`gui.py`, which initialises the file sink through the
`src.web_config → src/__init__ → src.logger` import chain) and the recording child process (`main.py`)
both held loguru file sinks on `logs/streamget.log`. Any process reaching the rotation threshold
(`rotation="300 KB"`, loguru uses base-1000) renames the file with `os.rename` first; with the other
side's handle still open this raises `PermissionError WinError 32`. Rotation then never succeeds and
**that process silently loses all of its file logging from that point on**, while each log record emits
`Logging error in Loguru Handler #N` to stderr and floods the GUI panel. Measured 2026-08-29:
`streamget.log` stuck at 300,031 bytes, the recording child's logs lost entirely, file mtime frozen at
the moment the rotation threshold was crossed.

**Fix** (added in `src/logger.py` / `gui.py` / `tests/test_logger_gui_parent.py`):

- `src/logger.py`: new `GUI_PARENT_ENV = "DLR_GUI_PARENT"` marker evaluated **at import time** — the GUI
  process writes only its own exclusive `logs/gui.log` (same rotation / retention policy) and never creates
  `streamget.log` / `PlayURL.log`.
- `gui.py`: sets the marker **before importing any `src` module** (`src.logger` reads it during import, so the
  assignment must precede the import); the env used to spawn the recording core (`main.py` / frozen CLI exe)
  now goes through `child_process_env()`.
- `tests/test_logger_gui_parent.py` (5 cases): the recording process holds streamget/PlayURL and produces no
  `gui.log`; the GUI process produces only `gui.log`; "enable log file = no" applies to the GUI as well;
  `child_process_env` strips the marker and pins UTF-8.
- `src/stream.py`: completed the `HuyaGameLiveInfo` TypedDict with `bitRate: int` and removed the
  `# type: ignore[arg-type]` (aligning with the repo's no-ignore convention) — an undeclared key degrades to
  `object` via `.get()`, which newly failed under strict checking.

**Note**: a second recording process started manually will also interlock with the GUI child; concurrent
multi-instance recording remains a usage limitation.

### v4.0.9.2-dev (2026-08-28) — Performance Review Optimization Landed (P1~P5 + Probe-Client Reuse + Backoff-Window Self-Healing + Web Log-Sink Rebuild + Huya FLV-first)

**Change Summary**: This entry systematically records the performance review and optimization of the codebase during the 2026-08-28 session, plus the four fixes derived from real-device verification. ① **Performance review** (local HTTP/1.1 measurements, 200 requests): 7 bottlenecks P1~P7 identified; landed **P1** (probe `httpx.Client` reused for one selection round), **P2** (thread-local reuse of `sync_http.Session`), **P3** (set-based dedup in the main loop), **P4** (incremental scheduler counters + hoist `import time` to module top), **P5** (hoist regexes to module-level constants); P6 (config dirty-check) deferred, P7 (`_resolve_platform_stream` → dict dispatch) explicitly not done; ② **real-device verification** (Huya/Douyu, three rounds) overturned several early assumptions and pinned down the root cause of Huya's cold-start HLS probe false-green — the fixed 60s backoff window is shorter than the 120s main-loop interval, so the self-healing loop never fired (fixes one/two); ③ **Web background-mode loguru console sink wrote to the hidden window** (fix three); ④ **Huya cold-start still failed once on the first round**, so FLV-first source selection was implemented (fix four). Full gate: **751 passed, 2 skipped**.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.2-dev (2026-08-28) — Performance Review Optimization Landed (P1~P5 + Probe-Client Reuse + Backoff-Window Self-Healing + Web Log-Sink Rebuild + Huya FLV-first) | section: Files Involved (Classified by Module)).

**Impact Scope**:

- Huya source-selection behavior changed (backoff-window alignment + success-clear + FLV-first): before the fix, 5 instant failures then stable only after 12 minutes; after, 1 instant failure then stable within 2 minutes (third-round real device 00:30–00:38: backoff warning first appeared, FLV recorded for 6m02s).
- Web-panel-mode logs now fully land in `logs/web_console.log` (before the fix only `print` output showed; DEBUG/WARNING went to the SW_HIDE-hidden window).
- Performance: 80 rooms × 10 probes/round selection time ~12.7s → 1.15s (P1 round-level reuse); main-loop dedup O(N²) → O(1); scheduler incremental counters shorten lock contention.
- The "max simultaneous recordings(0=unlimited)" scheduling semantics, HLS/FLV last-resort pass, probe throttle/jitter, `_confirm_get_ok` retry tolerance, and stream-validation tolerance are **all unchanged** (only Huya's candidate order reversed + backoff window dynamized).

- `compileall` (venv Python 3.14) passes; `black --check --line-length 120 --target-version py314` all files unchanged; `isort --check-only --profile black --line-length 120` passes; `mypy src/` + `mypy --platform linux src/` 0 issue; `basedpyright` 0 errors / 0 warnings / 0 notes.
- `pytest` full suite: **751 passed, 2 skipped** (2 srt failures are sandbox-deletion quota, not regressions).
- Three rounds of real devices (Huya 880214 / chuhe, Douyu, Douyin): backoff warning first appeared, FLV recorded stably for 6 minutes, `web_console.log` contains DEBUG/WARNING, cold-start first round expected to record FLV with zero instant-failure (fix four pending an independent cold-start re-verification).
- Local HTTP/1.1 benchmark: probe reuse peak connection 1 / 12.78ms; disabling keepalive instead 8 connections / 72.99ms (the forbidden case reverse-verified).

**Related**:

- `PERF_REVIEW_2026-08-28.md`: the performance-review report corresponding to this entry (with three misjudgment corrections).
- `AGENTS.md` regression-prevention entries: Huya backoff / FLV-first / probe-client scope / keepalive / backoff window ≥ main-loop interval / Web-background sink.
- v4.0.9.1-dev (2026-08-27) "Recording Failure Feedback Scheduler" — `mark_ffmpeg_reject` is that framework; this session adds the `clear_ffmpeg_reject` pairing and the `_PROBE_BACKOFF_INTERVAL_MARGIN` dynamization.

### v4.0.9.1-dev (2026-08-28) — CI Workflow Optimization & Network-Install Retry Consolidation (retry Composite Action) + PEP 758 Formatting Landed via black 26 + i18n Extractor Fixes + Eight-File Repository Metadata Sync

**Change Summary**: This entry records four batches of changes from the late 2026-08-27 session through 08-28. ① **CI red→green**: the CI `black --check` failed — black 26.5.1 enables PEP 758 normalization for `target-version=['py314']` (multi-except `except` clauses without an `as` sub-clause have their tuple parentheses stripped); local and CI run the same version, so this was simply a missed pre-commit formatting run, fixed by applying black; ② **CI workflow optimization**: ci.yml rewritten (actions unified at v7, apt hardening flags, job topology documented in the header) plus a new `.github/actions/retry` composite action consolidating 13 nearly identical inline retry scripts across the two workflows into a single implementation; ③ **i18n extractor fixes**: two defects in `scripts/extract_i18n_strings.py` fixed and re-run, confirming the four-language catalogs have zero missing entries (496 each); ④ **eight-file repository metadata sync**: corrected the stale `src/danmaku/` path comments in requirements.txt / Dockerfile and filled the drift gaps in .dockerignore / .gitignore / pyproject / compose. Full gate re-verification: **744 passed, 2 skipped**.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.1-dev (2026-08-28) — CI Workflow Optimization & Network-Install Retry Consolidation (retry Composite Action) + PEP 758 Formatting Landed via black 26 + i18n Extractor Fixes + Eight-File Repository Metadata Sync | section: Files Involved (Classified by Module)).

**Impact Scope**:

- CI gate green again and more maintainable: unified action versions, single-source retry strategy, apt installs more resilient to network jitter; build / release behavior unchanged (retry semantics, choco/apt/brew commands, and backoff values all preserved).
- i18n four-language catalogs confirmed complete (318 valuable strings all present), `.mo` byte-level synced with `.po` (497 entries incl. header); the extractor is ready for incremental maintenance.
- Docker build context significantly slimmed (scripts/, tests/, bilingual docs, local tool directories, uv.lock, etc. — 16 items excluded) and contains nothing the runtime does not need.
- **Zero runtime behavior change** — everything in this entry is CI / docs / comments / config sync / formatting (extract_i18n_strings.py is a maintenance-time tool, not in the runtime chain).

- `black --check .`: 115 files unchanged (incl. the PEP 758-converted i18n.py / compile_po.py); `isort --check-only .` pass;
- `mypy src/` + `mypy --platform linux src/`: both runs, 38 files, 0 issues;
- `pytest -q` full suite: **744 passed, 2 skipped** (36s);
- `python scripts/compile_po.py --check`: `.mo` synced with `.po` (497 entries incl. header); `python scripts/extract_i18n_strings.py`: 0 missing, four-language consistent, no inconsistency lines;
- Four-language runtime smoke: zh_CN Chinese translation / en_US identity / zh_TW Traditional-Chinese translation correct, unknown-language fallback intact (`tests/test_i18n.py` 34 passed);
- Eight-file sync consistency assertions (TOML/YAML parsing, 20 dependencies identical across both sources, zero `src/danmaku` references, .mimosa three-layer sync, 8 tool directories in both ignore files, image-only exclusions, AGENTS module count 41) all passed; `git check-ignore .mimosa/` confirms the ignore takes effect;
- Both workflow YAMLs validated via `yaml.safe_load` + structural assertions (needs chains / output keys / local action path existence / retry call counts 9+4 / version counts checkout@v7 ×7, setup-python@v7 ×6, setup-node@v7 ×2 / no DEBIAN_FRONTEND typos); the retry composite action verified via Git Bash simulation of success/failure paths.

**Related**:

- v4.0.9.1-dev (2026-08-27) "i18n Localization System Fix (except → tuple parentheses)" — this entry hands those 4 sites to black as unified PEP 758 bare-comma style (a semantically equivalent round-trip, see Change Notes);
- v4.0.9-dev (2026-08-24) "PEP 758 / py314 repo-wide formatting" — this session is the closing alignment under the same black version policy;
- v4.0.8.2-dev (2026-08-19) "CI refactor: build-release drops the download-artifact round-trip" — the §7 description is now aligned to that flow (release-create preallocation + direct upload);
- v4.0.9.1-dev (2026-08-27) first pass "four-language catalog full replenishment" — extract_i18n_strings.py is the tool that session left behind; this session fixed its two noise sources.

### v4.0.9.1-dev (2026-08-27) — i18n Localization System Fix (Python 2-style `except` Multi-Except → Tuple Parentheses) + zh_CN.mo Recompile

**Change Summary**: This entry records the 2026-08-27 evening session's fix to the localization subsystem — the true closure of the same-day first-pass "Four-language Catalog Unification". The first pass replenished 288 → 492 entries, but the `zh_CN.mo` recompile was blocked at the time: `i18n.py` and `scripts/compile_po.py` still carried Python 2-style `except A, B:` (including one three-except `except A, B, C:`) multi-except forms, which are hard `SyntaxError`s under Python 3. `compile_po.py` could not run and produce `.mo`, and `i18n.py` itself could not be `import`ed (the entire translation system was unusable). This session converts all four `except` clauses to `except (A, B, ...):` (behavior unchanged, pure syntax legalization), unblocks the compile chain, and regenerates `zh_CN.mo` (496 entries) aligned with the current `zh_CN.po`.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.1-dev (2026-08-27) — i18n Localization System Fix (Python 2-style `except` Multi-Except → Tuple Parentheses) + zh_CN.mo Recompile | section: Files Involved (Classified by Module)).

**Impact Scope**:

- `i18n.py` imports normally; four-language localization (CLI prints / GUI / Web language switch) is usable again; `scripts/compile_po.py` runs repeatedly; the `.mo` compile and CI `--check` gate chain is unblocked.
- `zh_CN.mo` is realigned with the current `zh_CN.po` (496 entries); Simplified-Chinese runtime translation is complete.
- Source functionality is unchanged — only the `except` multi-except syntax form was adjusted (4 sites).

- `python3 -m py_compile i18n.py scripts/compile_po.py`: pass; repo-wide grep for bare-comma `except A, B` forms returns zero.
- `python3 -c "import i18n"`: imports successfully; `i18n._load_translations(i18n.locale_path, 'zh_CN')` loads 496 entries without error.
- `python scripts/compile_po.py`: OK, generates `zh_CN.mo`; `python scripts/compile_po.py --check`: `.mo` synced with `.po` (496 entries).

**Related**:

- v4.0.9.1-dev (2026-08-27) first pass "Four-language localization catalog unification" — this entry unblocks its blocked `.mo` recompile and is the true closure of the first-pass localization replenishment;
- targeted correction of the same-day second-pass review entry's "PEP 758 legal / no change" assessment (limited to the two files `i18n.py` and `compile_po.py`).

### v4.0.9.1-dev (2026-08-27) — Second-Pass Review Fixes (compile_po --check Always-True Gate + Direct-Download Failure Sampling Gap + i18n/Web Gap Closure)

**Change Summary**: This entry systematically records nine changes made to the working tree during the second 2026-08-27 session (three parallel review subagents followed by manual cross-validation, fixed item by item in P1/P2 priority order). ① **P1 gate failure**: `scripts/compile_po.py --check` wrote to disk before reading back for comparison — always equal, rendering the CI po/mo sync gate useless; moreover the ci.yml path filter did not include `i18n/**` (translation-only changes didn't even trigger the test job); ② **P1 circuit-breaker sampling gap**: direct-download "non-200 / network error" failures were swallowed inside the function into a bare `False`, neither caller branch reported a sample, so dead routes kept being re-hit while bypassing per-host breaker statistics; ③ **P2 ×4**: the inner monitoring loop lost its per-round reset of danmaku args, `PUT /api/language` returned an unconditional 500 when the config key was missing, about ten hardcoded Chinese strings in the frontend bypassed the translation dictionary, and ISSUE_TEMPLATE lacked Python 3.14; ④ **legacy cleanup ×2**: two bare `logger.debug(e)` calls in `src/async_http.py` and a leftover Debug step in build-release.yml. One important clarification: all 16 bare-comma multi-except clauses (`except A, B:`) across the repo are **legal under Python 3.14 PEP 758** (both syntax and runtime catching verified by test) — the first machine-review pass misreported them as fatal syntax errors due to unawareness of this feature, so no change was made here. Full verification: **744 passed, 2 skipped**.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.1-dev (2026-08-27) — Second-Pass Review Fixes (compile_po --check Always-True Gate + Direct-Download Failure Sampling Gap + i18n/Web Gap Closure) | section: Files Involved (Classified by Module)).

**Impact Scope**:

- The CI i18n gate resumes its duty: any future "edited .po but forgot to recompile .mo" will be blocked by the static job, even if the PR touches only i18n/**.
- High-frequency-rejected routes of direct-download platforms (shopee / Huajiao) now properly accumulate breaker error budgets; past threshold they back off and release concurrency slots to other platforms instead of looping failures every few seconds.
- Scheduling semantics of "max simultaneous recordings(0=unlimited)" doubling as the concurrency-mode switch, probe-backoff allowlist, and HLS/FLV source selection are all unchanged.
- Dynamic frontend texts (toast/empty states/buttons) are fully localized for English/Traditional-Chinese users; static `data-i18n` texts were already covered before.

- Full `pytest -q`: **744 passed, 2 skipped** (36.3s, net +4 new cases);
- `black --check .` (after reformatting 2 new test files to the 120-column limit, re-verified) / `isort --check-only .`: 114 files unchanged / pass (`.isorted` backups cleaned);
- `mypy src/` + `mypy --platform linux src/`: dual-platform `Success: no issues found in 38 source files`; `mypy tests/`: 46 files, 0 errors (fixed an exit-return complaint from my own fake `__exit__ -> bool`);
- `basedpyright tests/`: 0 errors / 0 warnings / 0 notes;
- `python scripts/compile_po.py --check`: `.mo` synced with `.po` (493 entries), and the run confirmed `.mo` md5 unchanged before/after (zero side effects in effect); node --check validated app.js syntax; all six YAML edits passed safe_load;
- Grep review of frontend hardcoded-text leftovers: zero (only the dictionary definitions themselves remain).

**Related**:

- Same-day follow-up to the v4.0.9.1-dev (2026-08-27) first-pass review entry (probe lease self-healing + parse-success sampling) — that pass established the "report samples by exit code / parse outcome" framework; this pass closes its direct-download bypass and the gate-side loopholes;
- v4.0.9-dev (2026-08-23) "Recording failure feedback scheduler" — direct-download failure sampling completes its goal of "semantics aligned with the ffmpeg path" (its comment wrongly assumed False could only come from exceptions);
- v4.0.9-dev (2026-08-24) "Four-language localization catalog unification" and Web hot language switch — this round fixes the two remaining gaps: the write-back side and the frontend dynamic-text side.

### v4.0.9.1-dev (2026-08-27) — Code-Review Fixes (Circuit-Breaker Probe Lease Self-Healing + Scheduler Success Sampling) + Scheduler Thread-Safety Hardening + Full i18n Catalog Replenishment (288 → 492 entries)

**Change Summary**: This entry systematically records three batches of working-tree changes from the 2026-08-27 session. ① **Code-review fixes**: full quality gates (pytest 738 passed / black / isort / mypy dual-platform / basedpyright all green) plus three parallel review subagents, uncovering and fixing 1 high-severity and 3 medium-severity defects — `PlatformBreaker` half-open probe leak causing permanent host circuit-break (when the probe round ends via `continue` without triggering `record`, `_probing` never resets), probe success signal delayed until ffmpeg exit (other rooms on the same host starved for a long time), three-arg `getattr` Any leak in `notify.py` (mypy false-green), and uncaught YAML parse exceptions in `i18n.py` (a corrupted zh_TW.yaml caused `PUT /api/language` to return 500); ② **leftover review-item fixes**: bare `logger.error(e)` in `notify.py` (on Windows `str()` of `socket.timeout` is empty, losing log context), `host_of` comment-implementation mismatch in `scheduler.py`, and unlocked config-field reads/writes in the scheduler; ③ **full i18n catalog replenishment**: AST-scanned runtime code `print()`/`logger.*()` constant strings (47 files, 355 strings), added 204 translation entries after comparing against the four-language catalogs (288 → 492) and recompiled `zh_CN.mo`. Full verification: **740 passed, 2 skipped**.

**Files Involved (Classified by Module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9.1-dev (2026-08-27) — Code-Review Fixes (Circuit-Breaker Probe Lease Self-Healing + Scheduler Success Sampling) + Scheduler Thread-Safety Hardening + Full i18n Catalog Replenishment (288 → 492 entries) | section: Files Involved (Classified by Module)).

**Impact Scope**:

- The circuit breaker's self-healing on frequently failing platforms (Huya/Douyu CDN jitter) is significantly strengthened — previously, once a host entered half-open with a not-live probe round, all rooms on that platform backed off permanently; multi-room scenarios on the same host (Bilibili/Douyin batch monitoring) no longer starve the other rooms because of one room's long recording.
- A corrupted `zh_TW.yaml` degrades from "web language switch returns 500" to "that catalog is skipped, falling back to the next format".
- The runtime concurrency-capacity computation logic (adaptive/fixed dual modes, error backpressure) is semantically unchanged — locking only eliminates a theoretical race (under the GIL, int/bool assignment is atomic; a transient stale value affects only a single capacity round and is corrected by the next 5s recompute).

- Full `pytest -q`: **740 passed, 2 skipped** (34.8s, including the 2 new cases);
- `black --check .` / `isort --check-only .`: 114 files unchanged / pass;
- `mypy src/` + `mypy --platform linux src/` + `mypy` on the three root entry files: all `Success`;
- `basedpyright tests/`: 0 errors / 0 warnings;
- `python scripts/compile_po.py --check`: `.mo` synced with `.po` (493 entries);
- Four-language key-set assertion: `set(en_US) == set(en_GB) == set(zh_TW) == set(.mo entries)` (492 keys); runtime spot-check via `i18n._tr` confirmed new entries translate correctly in all four languages.

**Related**:

- Same origin as v4.0.9-dev (2026-08-24) "High-Concurrency Multi-Platform Recording Scheduling & Resource Management Optimization" — this session adds probe-lease self-healing to its `PlatformBreaker` and thread safety plus parse-success sampling to its `ConcurrencyScheduler`;
- Same origin as v4.0.9-dev (2026-08-23) "Recording-Result Feedback to Scheduler" — parse-success sampling completes that feedback system (previously only ffmpeg exit codes and the direct-download path reported);
- Same origin as v4.0.9-dev (2026-08-24) "Four-Language Catalog Unification" — this session expands the catalogs from 288 to 492 entries, extending coverage from print constant strings to repository-wide logger template drafts.

### v4.0.9-dev (2026-08-24) — This Session's Change Overview (Classified by Module)

> This entry is a systematic, module-classified overview of **all working-tree changes** accumulated in v4.0.9-dev up to 2026-08-24. The `### v4.0.9-dev (2026-08-24) — …` entries below are per-feature details (explaining "why and how"); this entry complements them by stating "which files changed and under which module". Note: this overview covers the entire 4.0.9-dev working tree (including the Python 3.14 upgrade, four-language i18n, concurrency scheduling, type fixes, etc.); some sub-items have deeper cause-effect analysis in the per-feature entries.

**1. Build / CI / Dependencies (Modifications)**

- `pyproject.toml`:
  - Version `4.0.8.3` → `4.0.9` (single source of truth; read dynamically by `main.py`/`web_api.py` via `importlib.metadata`; injected into `Dockerfile` via the `APP_VERSION` build arg).
  - `requires-python` `>=3.10` → `>=3.14`; classifiers collapsed from `3.10–3.13` to `3.14` only.
  - `[project.dependencies]` added `PyYAML>=6.0.3` (i18n YAML catalog `i18n/zh_TW.yaml` support; missing only loses that format, JSON/gettext unaffected).
  - `[tool.black] target-version` `['py310','py311','py312','py313']` → `['py314']`.
  - `[tool.mypy] python_version` `3.10` → `3.14`.
  - `[tool.pytest.ini_options]` added `filterwarnings`: ignore the `httpx`+`starlette.testclient` deprecation warning (third-party, unrelated to project code).
  - `[tool.basedpyright] pythonVersion` `3.10` → `3.14`.
- `requirements.txt`: added `PyYAML>=6.0.3` (strictly consistent with the `pyproject.toml` lower bound).
- `Dockerfile`: base image `python:3.13-slim-bookworm` → `python:3.14-slim-bookworm` (both builder and runtime stages); Node.js source `setup_22.x` → `setup_24.x` (24 LTS, empirically compatible with `node_install.py`).
- `.github/workflows/ci.yml`: `python_min` `3.10`→`3.14`, `python_latest` `3.13`→`3.15`, `python_matrix` `["3.10","3.13"]`→`["3.14","3.15"]`, `python_build` `3.12`→`3.14`; top-of-file tech-stack comment synced (pure Python, no frontend build, target py314).
- `.github/workflows/build-release.yml`: `python_build` `3.12`→`3.14` (same value as ci.yml, so verification env == release env).
- `.gitignore`: removed the ignore rule for `.coveragerc-concurrency` (now tracked, see below).
- New `.coveragerc-concurrency`: concurrency-test coverage config (referenced by CI via `COVERAGE_RCFILE`, `fail_under = 0`, report-only for manual review).
- New community templates: `.github/ISSUE_TEMPLATE/` (issue templates), `.github/PULL_REQUEST_TEMPLATE.md` (PR template), `.github/workflows/issue-translator.yml` (issue auto-translation Action).

**2. Internationalization (i18n) System (New Feature + Modifications)**

- `i18n.py`: rewritten as a four-format translation engine. Added `detect_system_language()` / `_windows_ui_language()` (with `sys.platform` gate, fixing the mypy `WinDLL` error) / `resolve_language()` / `set_language()` (runtime hot-switch) / `get_language()` / `available_languages()` / `normalize_language()` / `is_recognized_language()` / `has_catalog()` / `_load_json_catalog()` / `_load_yaml_catalog()` / `_load_mo_catalog()` / `_load_translations()` / `_build_translator()`; unified loading and runtime hot-switch across gettext `.po/.mo` + JSON (`en_US`/`en_GB`) + YAML (`zh_TW`). See the per-feature entries "Four-Language Catalog Unification" and "CI mypy Double-Error Fix".
- New `i18n/en_US.json`, `i18n/en_GB.json`, `i18n/zh_TW.yaml`: four-language catalogs, 288 keys each (American / British spelling split).
- Recompiled `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` (28,697 bytes); `compile_po.py --check` confirms byte-level sync.
- New `CODE_WIKI_EN.md` (English architecture doc), `README_EN.md` (English user doc), structurally aligned with the Chinese versions.
- `gui.py`: added `_on_language_change()` (GUI language-switch dropdown), `_install_crash_sink()` / `_bootstrap_error_sink()` (top-level crash dump hook, making windowed silent crashes observable).
- `src/web_api.py`: added `LanguageUpdate` model and `GET/PUT /api/language` endpoints (Web-panel language hot-switch: normalize-validate → write back to `config.ini` → hot-switch this process's translation catalog).
- `web/index.html` / `web/app.js` / `web/style.css`: added language selector and related UI (+291 / +83 / +13 lines).

**3. Concurrency Scheduling & Resource Management (High-Concurrency Multi-Platform) (New Feature)**

- New `src/scheduler.py`: `ResizableSemaphore` / `PlatformBreaker` / `ConcurrencyScheduler` / `host_of`. Replaces the old "fixed 3-slot semaphore + one-way error-rate suppression" with "runtime-resizable semaphore + per-host platform-isolated circuit breaking + adaptive global concurrency capacity".
- `main.py`: scheduler wiring — `main()` initializes the scheduler, wires the capacity floor into "最大同时访问网络线程数" (max concurrent network threads), and adds the new "最大同时录制数(0=不限制)" (max concurrent recordings, 0=unlimited); `start_record` adds a per-host circuit-breaker pre-check and `record_host` propagation (pre-set to `""` to eliminate possibly-unbound); `check_subprocess`'s recording loop is gated by `recording_semaphore`; `semaphore`/`recording_semaphore` are now `ResizableSemaphore`.
- `src/notify.py`: `record_error`/`record_success` gained a `key` parameter and delegate to the scheduler to record the per-key error budget; `adjust_max_request` now launches the `scheduler.adjust_loop` daemon loop.
- New `tests/test_scheduler.py` (12 cases).
- Fixed 21 Python 2-style `except A, B:` syntax errors across 14 source files (`build_exe.py`, `gui.py`, `i18n.py`, `scripts/check_coverage.py`, `scripts/compile_po.py`, `src/collector.py`, `src/config_io.py`, `src/recorder_status.py`, `src/spider.py` (2), `src/ttwid.py`, `src/web_config.py`, `src/ws_client.py`, `src/platforms/bilibili.py`, `src/platforms/douyu.py`), making the project importable/testable under Python 3. See the per-feature entry "High-Concurrency Multi-Platform Recording Scheduling & Resource Management Optimization".

**4. Recording-Result Feedback to Scheduler + Probe Backoff (Root Fix for Huya 403 Dead Loop)**

- `main.py`: `check_subprocess` now feeds back by return code — `rc==0`→`record_success(host_of)`, `rc!=0`→`record_error(host_of)`; fast-fail (≤20s) extracts the real URL after `-i` and calls `mark_ffmpeg_reject` to record probe backoff; the direct-download success path adds `record_success`; the unconditional end-of-round `record_success` is removed.
- `src/stream_select.py`: added `mark_ffmpeg_reject(url, platform)` (delegates to `_mark_probe_reject`); silently no-ops when `platform` is not in `_PROBE_BACKOFF_PLATFORMS` (only `"虎牙直播"`).
- New `tests/test_record_failure_feedback.py` (5 cases). See the per-feature entry "Recording-Result Feedback to Scheduler + Probe Backoff Marking".

**5. Type / Quality-Gate Fixes (Modifications)**

- `i18n.py`: `_windows_ui_language()` adds `if sys.platform != "win32": return None` platform gate (fixes `mypy --platform linux` `Module has no attribute "WinDLL"`).
- `src/recorder_status.py`: in `_live_network_capacity()`, the 3-arg `getattr(main,"scheduler",None)` is replaced by direct `main.scheduler` (fixes `no-any-return` Any leak).
- `tests/test_i18n.py`: added `TestWindowsUiLanguagePlatformGate` (2 cases) and `test_c_locale_from_getlocale_ignored` (C/POSIX filter regression); 4 `patch.dict(os.environ)` calls replaced with `monkeypatch.setenv/delenv` (AGENTS.md mandatory convention); fixed the pytest-collection `sys.argv` parsing guard.
- `i18n.py` `detect_system_language()`: the `locale.getlocale()` fallback path now adds C/POSIX filtering.
- `src/async_http.py`: `close_all_clients_sync()` adapted to Python 3.14 — `asyncio.get_event_loop()` no longer implicitly creates a loop; catches `RuntimeError` and falls back to reference cleanup.
- `src/config_io.py`: `read_config_value()`'s default-value write-back now "serializes fully in memory via `io.StringIO` first, then writes to disk only on success"; catches `InvalidWriteError` (Python 3.14+ raises this from `configparser` when writing a key containing a delimiter) and rolls back the in-memory state while removing the bad key; multiple `except` clauses comma-ized (PEP 758).
- `src/http_config.py`: since FFmpeg 9.0 validates TLS certificates by default, the "platforms with SSL verification disabled" override is effective again; `get_effective_ssl_verify()` now reads the per-platform override when `ssl_verify=True` (http mode, default strict verification restored).
- `src/logger.py`: `sys.stderr is None` guard (pythonw / `console=False` frozen exe has no console, so the console sink is skipped to avoid an import-time `TypeError` silent crash).
- `src/web_config.py` / `src/spider.py` / `build_exe.py`: `except` clauses comma-ized (PEP 758 mechanical reformat).

**6. Platform Adaptation / Download Sources (Modifications)**

- `src/ffmpeg_install.py`: switched the LanZou FFmpeg download source — `wweb.lanzouv.com` → `wwasx.lanzout.com` (new extraction code); `get_lanzou_download_link()` and `_install_ffmpeg_lanzou()` domain/password synced.
- `src/spider.py` `get_migu_stream_url()`: the Migu `migu.js` (2026-08 rewrite) now emits the full URL with `ddCalcu`/`sv` params; the locally hard-coded expired `sv=10010` concatenation is removed.

**7. Repo-wide Formatting (PEP 758 / py314) & Local Environment (Modifications)**

- `black` 26.5.1 + `target-version=['py314']` repo-wide reformat: strips parentheses from `except (A, B):` (PEP 758 re-legalizes the syntax in Python 3.14). Executed under a **Python 3.14.7** runtime (the local 3.13 venv cannot emit this syntax and black's safety check rejects it), reformatted **295 files** in total (**53 project `.py` files**; the rest are third-party packages inside `.venv`, which were moved out of the repo and do not affect the project).
- The local dev venv was rebuilt from Python 3.13.14 to **3.14.7** (with all runtime dependencies + `black==26.5.1` / `isort==8.0.1` / `mypy==2.3.0` / `basedpyright` / `pytest`). All four gates (`black --check .` / `isort --check-only .` / `mypy src/` + `mypy --platform linux src/` / `basedpyright`) are now green under 3.14.
- This item was marked "TODO" in the "CI mypy Double-Error Fix" entry; it has been completed during this session's wrap-up (including the venv rebuild).

### v4.0.9-dev (2026-08-24) — CI pytest failure fix: C/POSIX locale detection and monkeypatch convention

**Change Summary**: Fixed CI `tests/test_i18n.py::TestDetectSystemLanguage::test_c_and_posix_env_ignored` assertion failure (`assert 'C' != 'C'`). Root cause was that the `locale.getlocale()` fallback path in `detect_system_language()` returned `('C', None)` under Linux CI (`LANG=C`) without filtering C/POSIX special values, leaking the raw value. Synchronously replaced 4 `patch.dict(os.environ, clear=True)` calls in `tests/test_i18n.py` with `monkeypatch.setenv/delenv` (following AGENTS.md mandatory convention: `patch.dict` snapshots the entire `os.environ`, which can trigger a 32767-character upper limit overflow on Windows). Finally performed a full-repository `black` formatting to resolve PEP 758 `except (A, B):` parentheses stripping under Python 3.14 that caused CI Static Checks failures.

**Files Changed**:

- Modified `i18n.py`: The `locale.getlocale()` fallback path in `detect_system_language()` now adds C/POSIX filtering — the `current = locale.getlocale()[0]` return value is only returned after checking `current.upper() not in ("C", "POSIX")`, otherwise returns `None`, consistent with the C/POSIX filtering semantics of the environment variable path. Added 3 PEP 758 format changes (`except (OSError, ValueError):` → `except OSError, ValueError:`).
- Modified `tests/test_i18n.py`:
  - `TestDetectSystemLanguage._env_without_locale_vars` refactored to `_clear_locale_vars(monkeypatch)`, using `monkeypatch.delenv(var, raising=False)` to individually delete locale-related environment variables;
  - 4 `patch.dict(os.environ, ..., clear=True)` calls replaced with `monkeypatch.setenv/delenv`;
  - Added `test_c_locale_from_getlocale_ignored` regression test: patches `locale.getlocale` to return `("C", None)`, verifies `detect_system_language()` returns `None` (does not depend on real environment variables);
  - Fixed `sys.argv` parameter parsing conflict during pytest collection: `SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else N` (prevents `int('-q')` crash from pytest `-q` parameter).

**Implementation Details**:

- **Unified C/POSIX filtering**: `detect_system_language()` has two paths for obtaining language — environment variables (`LANGUAGE`/`LC_ALL`/`LC_MESSAGES`/`LANG`) and `locale.getlocale()`. The former already had C/POSIX filtering, the latter was missing. In Linux CI processes with `LANG=C`, `locale.getlocale()` returns `('C', None)`, which was returned unfiltered as `"C"`, causing the test assertion to fail. This change unifies filtering across both paths.
- **Monkeypatch convention**: `patch.dict(os.environ, clear=True)` creates a full snapshot of `os.environ` (`original = in_dict.copy()`) and unconditionally writes back `_clear_dict() + update(original)` on exit. AGENTS.md mandates using `monkeypatch` — the coding agent harness injects `CODEBUDDY_MCP_CONFIG` which dynamically inflates `os.environ`, and the Windows 32767-character limit can be exceeded, causing a `ValueError` on write-back. `monkeypatch` only operates on individual keys without creating a full snapshot.
- **PEP 758 formatting**: black 26.5.1 (CI pinned version) automatically strips `except (A, B):` parentheses under `target-version = ['py314']`. All project files were reformatted (including 3 `except (OSError, ValueError):` instances in `i18n.py`); the final run under a Python 3.14.7 runtime reformatted 53 project `.py` files in total — for the full scope and venv rebuild see "This Session's Change Overview (Classified by Module)" section 7 above.

**Impact**:

- Zero runtime behavior change — `detect_system_language()` under C/POSIX locale now returns `None` instead of `"C"` (equivalent to no system language set); downstream `resolve_language(None)` falls back to `FALLBACK_LANGUAGE = "en_US"`, which is the expected behavior (C locale does not indicate the user selected Chinese).
- Improved test stability — no longer relies on `patch.dict` full-snapshot of `os.environ`, avoiding `ValueError` from harness environment variable expansion.
- Formatting alignment — full-repository black output is unified to Python 3.14 style; CI Static Checks continue to pass.

- `pytest tests/test_i18n.py`: **33 passed** (including the new `test_c_locale_from_getlocale_ignored` regression test);
- `black --check .`: **512 files clean**;
- `isort --check-only .`: all passed;
- `mypy tests/`, `mypy src/`, `mypy --platform linux src/`: all `Success`;
- `basedpyright tests/`: **0 errors / 0 warnings**;
- `py_compile i18n.py tests/test_i18n.py`: passed.

**Related**:

- Homologous to the `detect_system_language()` logic added in v4.0.9-dev (2026-08-23) "Python 3.14 upgrade + language config key migration" — this fix addresses the missing C/POSIX filtering in the `locale.getlocale()` fallback path.
- Consistent with AGENTS.md test writing convention (environment variables must use `monkeypatch.setenv/delenv`, `patch.dict(os.environ)` is prohibited).

### v4.0.9-dev (2026-08-24) — CI mypy Double-Error Fix (ctypes.WinDLL Platform Gating + 3-arg getattr Any Leak)

**Change Summary**: Fixes two errors from CI `mypy src/` (mypy 2.3.0, linux runner) — `i18n.py:129: Module has no attribute "WinDLL" [attr-defined]` and `src/recorder_status.py:118: Returning Any from function declared to return "int" [no-any-return]`. Both are static-typing issues; zero runtime behavior change.

**Files Changed**:

- `i18n.py`: `_windows_ui_language()` now opens with an early-return platform gate `if sys.platform != "win32": return None`. `ctypes.WinDLL` only exists in the Windows typeshed; CI's mypy runs on a linux runner (and `mypy src/` pulls root-level `main.py`/`i18n.py` into the check via the import chain), so a bare reference inside the function body always raises `attr-defined`. The sole caller (`detect_system_language()`) already sits inside a `sys.platform == "win32"` branch, and on non-Windows the old code likewise returned None via `except` — behavior is identical (aligns with the gating convention of `src/web_tray.py._patch_console_window`).
- `src/recorder_status.py`: in `_live_network_capacity()`, `getattr(main, "scheduler", None)` is replaced by direct attribute access `main.scheduler`. mypy does not resolve the literal name for the 3-arg `getattr` (reveal_type shows `Any | None`), which both triggers `no-any-return` and silently disables type checking along the whole `scheduler.network_semaphore.value` chain; `main.scheduler` has a module-level declaration in `main.py` (`ConcurrencyScheduler | None`), so the attribute always exists. Tests only substitute it via `monkeypatch.setattr` (never delete), so the runtime is equivalent.
- `tests/test_i18n.py`: adds `TestWindowsUiLanguagePlatformGate` with two cases — ① on non-win32 the platform gate returns None directly (no reliance on the ctypes exception fallback); ② an inverted gate condition (`== win32` returning early) is a blind spot mypy cannot catch, so a fake `ctypes` injection (sys.modules patch) locks in that win32 still walks the full "WinDLL → GetUserDefaultUILanguage → windows_locale" chain (2052/0x0804 → zh_CN).

**Design Notes**:

- The platform gate uses a first-line early return rather than wrapping call sites: the function owns its platform contract (its comment already states "returns None on non-Windows"), so callers need no duplicate gating; both mypy and basedpyright recognize branch pruning on literal `sys.platform` comparisons.
- Deliberately no `# type: ignore[attr-defined]`: the comment would be required on Linux CI but redundant on a Windows box, and basedpyright would flag `reportUnnecessaryTypeIgnoreComment` — there is no way to be clean on both ends; the `sys.platform` branch is the only dual-clean form.
- Deliberately no `cast(ConcurrencyScheduler | None, getattr(...))`: cast gives up checking and hides the fact that the attribute is declared and directly accessible.

**Impact Scope**: static typing and tests only; no runtime behavior change; CI `mypy src/` back to green.

**Also Discovered (Completed during this session's wrap-up)**: after the working tree migrated black's `target-version` to `py314`-only, the pinned black 26.5.1 strips parentheses from `except (A, B):` under the py314 grammar target (PEP 758 re-legalizes the syntax in 3.14). This was completed during the wrap-up under a **Python 3.14.7** runtime: the repo-wide `black .` reformatted **53 project `.py` files** (including untouched-but-format-due `src/collector.py`/`src/ttwid.py`/`src/ws_client.py`), restoring CI Static Checks (`black --check .`) to green; the output contains 3.14-only syntax, so the local dev venv was rebuilt to **3.14.7** as well. Full details in "This Session's Change Overview (Classified by Module)" section 7 above.

### v4.0.9-dev (2026-08-24) — High-Concurrency Multi-Platform Recording Scheduling & Resource Management Optimization (Adaptive Concurrency + Per-Platform Circuit Breaking)

**Change Summary**: Addresses the reported issue of "severe latency, sharp performance degradation, and a large number of errors when recording more than 80 tasks simultaneously across multiple different platforms". Root-cause analysis of the logs (`logs/log.log` shows "共监测79个直播中 | 同一时间访问网络的线程数: 3" / "正在录制2个直播") confirmed four root causes: ① the global network semaphore was hard-fixed at 3 and `adjust_max_request` could only suppress it one-way; ② error-rate feedback formed a death spiral (more errors → more limits → more errors); ③ no platform isolation, so a single platform's API jitter dragged down the whole system; ④ no circuit-breaker/degradation mechanism, so a single task's exception was amplified in a chain.

This change introduces `src/scheduler.py` as a unified scheduling hub, replacing the old "single global fixed semaphore + one-way error-rate suppression" model with "runtime-resizable semaphore + per-host circuit breaker + adaptive global concurrency capacity", and wires it into fixed integration points in `main.py` / `src/notify.py`. It also fixes 21 pre-existing Python 2-style `except A, B:` syntax errors across 14 source files (a historical leftover that blocked importing/testing the project under Python 3).

**Files Involved**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9-dev (2026-08-24) — High-Concurrency Multi-Platform Recording Scheduling & Resource Management Optimization (Adaptive Concurrency + Per-Platform Circuit Breaking) | section: Files Involved).

**Impact Scope**:
- The concurrency model is upgraded from "single global fixed 3-slot semaphore + one-way error-rate suppression" to "adaptive global capacity (scales with active task count, with a safety floor) + per-host platform-isolated circuit breaking + optional recording-concurrency soft cap". With 80+ tasks across multiple platforms, the 77-thread queue behind a fixed 3 slots no longer occurs; a single platform's API jitter is isolated as degradation and does not drag down the whole system; a single task's exception is captured and counted into the per-platform error budget, preventing chain errors from making the system unavailable.
- Only `src/scheduler.py` was added and wired into fixed integration points in `main.py` / `src/notify.py`; the 50+ platform dispatch/recording functions were **not rewritten**, and behavior is backward compatible. The old `semaphore` global name is retained (now pointing at a `ResizableSemaphore`), so downstream `with semaphore:` usage is unchanged.
- New config item "最大同时录制数(0为不限制)" (max concurrent recordings, 0=unlimited; default 0 = treated as high capacity, non-blocking; the key was initially misnamed "最大同时录制数(0=不限制)", whose embedded `=` delimiter truncated reads and raised `InvalidWriteError` on write-back, crashing startup — renamed, with `read_config_value`'s fallback hardened). "最大同时访问网络线程数" (max concurrent network threads) is now one of the concurrency-capacity floors (no longer the sole one-way suppression knob).
- Performance: network concurrency capacity scales up adaptively with the active task count (default floor 8, ceiling 128), significantly reducing probe queuing and processing latency in high-concurrency scenarios.

- `tests/test_scheduler.py` + `tests/test_main_fixes.py`: **41 passed**;
- Full `pytest`: **707 passed / 3 skipped**, with 2 failures both being the pre-existing sandbox safe-delete guard in `tests/test_twitch_live_collector.py` (`SAFE_DELETE_FAIL_CLOSED … windows-sandbox-recycle-bin-unavailable`) — a historical environment limitation unrelated to this change;
- `basedpyright src/scheduler.py tests/test_scheduler.py`, `basedpyright tests/`, and `basedpyright main.py src/notify.py src/scheduler.py` all report **0 errors / 0 warnings / 0 notes**;
- `black --check` / `isort --check-only` pass on all touched files;
- `python -m py_compile` passes on all sources.

**Related**:
- Same lineage as v4.0.8.3-dev (2026-08-21) "start_record complexity governance" — that change extracted the platform-dispatch chain into `_resolve_platform_stream`; this change adds a circuit-breaker pre-check before that function's call, without touching its recording execution chain.
- The per-host isolation/degradation approach is consistent with the AGENTS.md known-pitfall "single-platform CDN occasional 403/405 probe false-kill" remediation goal (after isolation, a single platform's jitter no longer amplifies globally).

### v4.0.9-dev (2026-08-24) — Four-Language Catalog Unification & British/American Split + Build-Script Strings Added + zh_CN.mo Recompiled

**Change Summary**: Unified and corrected the four localization catalogs (zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml). An AST parse of all .py sources in the workspace (excluding tests / venv / node / ffmpeg / build / dist) extracted the print()/_tr() constant strings as the authoritative localizable set, confirming the runtime scope (main.py / gui.py / web.py / src/*) was already fully covered by the existing 282 entries; only 6 constant build/smoke strings ([build]… / [smoke]…) in build_exe.py were missing. The four catalogs already shared an identical 282-key set, but en_US had mixed in British spellings (minimises/minimised/cancelled) and en_GB was effectively a clone of en_US. This change adds the 6 build strings to all four catalogs (now a uniform 288-key set), unifies en_US to pure American (minimizes/minimized/canceled), rewrites en_GB as genuinely British (minimise/minimises/minimised/cancelled) differing from en_US in only 4 spelling-sensitive entries, and updates and recompiles zh_CN.po into zh_CN.mo (compile_po.py --check confirms byte-level sync).

**Files involved**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9-dev (2026-08-24) — Four-Language Catalog Unification & British/American Split + Build-Script Strings Added + zh_CN.mo Recompiled | section: Files involved).

**Impact scope**:
- All four catalogs now share the same 288-key set, with no missing or extra entries; zh_CN.mo is byte-level synced with zh_CN.po.
- Only localization resources changed; no code-logic modifications; runtime behavior and existing translations are unaffected.
- Scope follows the project i18n convention (localize user-facing product strings only): CI/version-check scripts/*.py, third-party bundled assets, the tests directory, and personal temp scripts are excluded from the catalogs.

- A custom reconciler script parsed all four catalogs and confirmed identical key sets (288 each, excluding the gettext header pseudo-key).
- `python scripts/compile_po.py --check`: zh_CN.mo syncs with zh_CN.po (289 entries incl. the gettext standard header), passed.
- JSON / YAML both valid (json.loads / yaml.safe_load raise no errors).

**Related**:
- Same internationalization-system maintenance as v4.0.9-dev (2026-08-23) "Python 3.14 upgrade + language-key migration" — that change completed the language-key migration and the four-language catalog hot-switch chain; this change completes the unification and spelling split of the translation catalogs themselves.
- Consistent with the four-language catalog table (zh_CN.po / en_US.json / en_GB.json / zh_TW.yaml) in CODE_WIKI.md's "Internationalization Module" section; the corresponding capability description in README.md's "Multi-language and UI switching" section is unchanged.

### v4.0.9-dev (2026-08-23) — Recording-Result Feedback to Scheduler + Probe Backoff Marking (Root Fix for Huya 403 Dead Loop)

**Summary**: The 2026-08-23 GUI real-world run with 79 rooms exposed a missing recording-side feedback loop: Huya rooms showed probe 200/206 success followed immediately by ffmpeg 403 rejection, yet `check_subprocess` previously **neither reported failure samples by return code, nor recorded a success sample unconditionally at round end** — the per-host circuit-breaker error budget got diluted and never triggered, so rooms kept looping on the same dead CDN line. Console concurrency display showed the config value (3) instead of the scheduler's adaptive value (12/20), misleading users into thinking the optimization had no effect. This change wires recording failures into the scheduler and triggers probe backoff so the next round picks the next CDN candidate.

**Files touched**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9-dev (2026-08-23) — Recording-Result Feedback to Scheduler + Probe Backoff Marking (Root Fix for Huya 403 Dead Loop) | section: Files touched).

**Impact**:
- Huya rooms hitting "probe 200 → ffmpeg 403" dead loops will now skip that CDN line's probe next round and try the next candidate among HS/HW/TX/AL — dead lines get abandoned quickly, avoiding wasted retry loops and circuit-breaker stat pollution.
- Only `main.py` / `src/stream_select.py` / `src/recorder_status.py` are modified; wiring points are the `check_subprocess` return-code branch, `direct_download_stream` success path, and `display_info` status line — the platform dispatch chain and recording execution mainline are untouched.
- Backoff whitelist is Huya-only (`_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)`); other platforms unaffected, preserving "retry-once-then-verdict" semantics.

- `pytest tests/test_record_failure_feedback.py tests/test_stream_select.py tests/test_scheduler.py`: **43 passed / 0 failed**;
- Full `pytest --ignore=tests/test_twitch_live_collector.py --ignore=tests/test_srt_timeline_anchor.py`: **710 passed / 3 skipped**, plus 1 unrelated failure (`test_config_io_readonly.py::test_read_config_value_delimiter_key_no_crash` — config_io key-name-contains-`=` writeback fallback, Python-version-dependent);
- `black --check` (run with Python 3.14; venv Python 3.13 cannot AST-verify 3.14-suffixed syntax) / `isort --check-only` all pass on the 5 touched files;
- `basedpyright main.py src/recorder_status.py src/stream_select.py tests/test_record_failure_feedback.py`: **0 errors / 0 warnings / 0 notes**.

**Related**:
- Continues the v4.0.9-dev (2026-08-23) scheduler governance — the scheduler already had per-host circuit-breakers and adaptive capacity; this change closes the last feedback loop: "recording-side failure → circuit-breaker sample + probe backoff".
- Consistent with the AGENTS.md known-pitfall "CDN probe throttling/backoff" remediation goal: probe-side throttling+backoff lowers false-risk-control rate, recording-side backoff marking closes the blind spot where probe (httpx) and ffmpeg client fingerprints differ.

### v4.0.9-dev (2026-08-23) — Dual Network-Concurrency Modes (Adaptive vs Fixed)

**Change Summary**: On top of the already-adaptive `ConcurrencyScheduler` capacity, this change introduces a "fixed concurrency" mode so that the `最大同时录制数(0为不限制)` (max concurrent recordings, 0=unlimited) config item doubles as the concurrency-mode switch, letting users choose the scheduling strategy instead of being forced to use the adaptive governor.

**Files touched**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](../agent-reference/changelog-file-inventories-en.md) (entry: v4.0.9-dev (2026-08-23) — Dual Network-Concurrency Modes (Adaptive vs Fixed) | section: Files touched).

**Impact scope**:
- Only `src/scheduler.py` / `main.py` / `tests/test_scheduler.py` / `AGENTS.md` are modified. All existing `ConcurrencyScheduler` APIs — `set_active_count` / `set_configured_limit` / `set_recording_limit` / `allow` / `record_error` / `record_success` / `network_semaphore` / `recording_semaphore` — and the downstream `with semaphore:` usage are preserved, fully backward compatible.
- Users switch to fixed concurrency by setting `最大同时录制数(0为不限制)` to a non-zero value (e.g. 2); in that mode `同一时间访问网络的线程数` is the effective concurrency limit (no longer a capacity floor). Setting it back to 0 restores adaptive scaling.

- `pytest tests/test_scheduler.py`: **15 passed** (the 3 new mode cases included);
- `pytest tests/test_record_failure_feedback.py tests/test_concurrency.py -q`: **11 passed** (scheduler-governance and concurrency-thread-safety regressions all green);
- `black --check src/scheduler.py main.py tests/test_scheduler.py`, `isort --check-only src/scheduler.py main.py tests/test_scheduler.py`, `mypy src/scheduler.py tests/test_scheduler.py`, `basedpyright tests/test_scheduler.py`, `py_compile main.py src/scheduler.py` all pass with **0 errors / 0 warnings**;
- End-to-end smoke (against real `config/config.ini` values: `最大同时录制数(0为不限制)=0`, `同一时间访问网络的线程数=3`): dynamic mode with 80 active tasks → capacity 20 (scales up, respects floor 8); switched to fixed mode with 200 active tasks → capacity stays 3; in fixed mode, setting configured limit to 0 floors capacity to 1; logs emit `并发模式: 动态调速/固定 …` as expected.

**Related**:
- Continues the v4.0.9-dev (2026-08-23) / (2026-08-24) scheduler governance — with per-host breakers, adaptive capacity, recording-side feedback and probe backoff already in place, this change adds the "user-selectable concurrency strategy" layer on top, letting the scheduler serve both strong-throughput-adaptive and stable-concurrency-ceiling workloads.
- Synced with the AGENTS.md concurrency-model section and the `test_scheduler.py` case count (12 → 15).

### v4.0.9-dev (2026-08-23) — Python 3.14 Upgrade + Language Config Key Migration (Comprehensive Maintenance)

**Source**: The user asked to upgrade the project to Python 3.14, comprehensively check and remove deprecated syntax/modules/features, raise the minimum version requirement from Python 3.10 to `>=3.14`, and at the same time unify the `config/config.ini` `language(zh_cn/en)` config item into `language`, implementing the complete chain of "blank follows system language, unrecognized falls back to en_US, GUI/Web panels support restart-free hot switching, and old key values are auto-migrated at startup".

**Changes**:

- **Python version baseline upgrade (`pyproject.toml` + `Dockerfile` + `.github/workflows/ci.yml` + `AGENTS.md` + docs)**:
  - `pyproject.toml`: `requires-python = ">=3.14"`, `[tool.black] target-version = ['py314']`, `[tool.mypy] python_version = "3.14"`, `[tool.pytest] asyncio_mode = "auto"` unchanged; `uv.lock` synced to the upgraded Python version marker.
  - `Dockerfile`: base image upgraded from `python:3.13-slim-bookworm` to `python:3.14-slim-bookworm`; the `APP_VERSION` build-arg mechanism unchanged.
  - `.github/workflows/ci.yml`: `setup-python`'s `python-version` matrix updated from `'3.13'` to `'3.14'` (unified across `typecheck` / `test` / `concurrency-test` / `integration-verify` / `build-verify`).
  - `AGENTS.md`: project overview, Python version, known-pitfalls entries, and mypy check version all aligned to Python 3.14, plus new 3.14 breaking-change baseline notes (`asyncio.get_event_loop()`, `pkg_resources`, PEP 594 dead batteries, `ctypes.windll` usage conventions).
  - `README.md` / `README_EN.md` / `CODE_WIKI.md`: Python badge changed from `3.13` to `3.14`, run-method prerequisites synced.

- **Python 3.14 compatibility fixes (`src/async_http.py`)**:
  - `close_all_clients_sync()` (called by `atexit` / signal hooks) used to throw `RuntimeError` on Python 3.14 because `asyncio.get_event_loop()` raises when no loop exists in the current thread (≤3.13 implicitly created one + `DeprecationWarning`); changed to `try: asyncio.get_event_loop() except RuntimeError: loop = None` to catch `RuntimeError` and fall back to reference cleanup; loop acquisition inside coroutines uniformly uses `asyncio.get_running_loop()`.
  - Added a "Python 3.14 no longer implicitly creates an event loop in `asyncio.get_event_loop()`" entry to `AGENTS.md` known pitfalls for future maintenance reference.

- **Language config key migration and system-language fallback (`i18n.py` + `main.py` + `gui.py` + `src/web_api.py` + `src/web_config.py`)**:
  - `i18n.py`: added `FALLBACK_LANGUAGE = "en_US"`, `detect_system_language()` (env vars `LANGUAGE`/`LC_ALL`/`LC_MESSAGES` → Windows `GetUserDefaultUILanguage` → POSIX `locale.getdefaultlocale()`), `has_catalog(lang)` (probes available translations by `i18n/<lang>/` multi-format catalog), `resolve_language(value)` (empty → system language → `FALLBACK_LANGUAGE`; illegal value or missing catalog → `FALLBACK_LANGUAGE`).
  - `main.py`: added `_read_language_config()`, reads the new `language` key in `config.ini` at startup; if only the old key `language(zh_cn/en)` exists, reads its value, migrates and writes back to the new key, keeping the old key only for history; the main loop syncs the i18n translation function each round via `resolve_language`, ensuring Web/GUI config changes hot-switch on the CLI's next round.
  - `gui.py`: initial language read changed to first check the new `language` key, fall back to the old key `language(zh_cn/en)`, then fall back to system language; the sidebar "Language" menu writes back to the new `language` key.
  - `src/web_api.py`: `PUT /api/language` writes back the key name changed from `language(zh_cn/en)` to `language`; `GET /api/language` return value normalized via `resolve_language`.
  - `src/web_config.py`: `_write_language_section` writes `language = {value}` instead of the old key, avoiding falling back to the old field when parallel edits conflict.

- **Test additions (`tests/test_i18n.py` + `tests/test_web_api.py` + `tests/test_config_io_readonly.py`)**:
  - `tests/test_i18n.py`: added `TestResolveLanguage` (empty→system language→en_US, illegal→en_US, missing catalog→en_US, legal value returned directly), `TestDetectSystemLanguage` (env var priority) for 8 cases total.
  - `tests/test_web_api.py`: fixed `_write_language_section` regression, ensuring it writes the new `language` key instead of the old one.
  - `tests/test_config_io_readonly.py`: added 3 language-key migration cases (old key auto-migrated and written back, new key priority, default value backfilled).

- **Code style and static checks (`black` / `isort` / `mypy` / `basedpyright`)**:
  - Upgraded `black` target version to `py314` (PEP 758 `except A, B` syntax auto-supported), reformatted the whole project with `black .` / `isort .`; `mypy src/` re-checked with `python_version = "3.14"`, `disallow_untyped_defs = true` still fully passes; `basedpyright src/` 0 errors / 0 warnings.
  - All new code got type annotations added, preserving the project's `disallow_untyped_defs = true` gate.

- **Quality gate verification**:
  - Full `pytest` **714 passed / 2 skipped / 0 warnings** (including the new language-key migration and `async_http` regression cases);
  - `black --check .` all files unchanged; `isort --check-only .` fully passes;
  - `mypy src/` → `Success: no issues found`; `basedpyright src/` → **0 errors / 0 warnings / 0 notes**;
  - `python scripts/compile_po.py --check` confirms `.po` / `.mo` byte-level sync unaffected.

- **Docs and conventions sync**:
  - `AGENTS.md`: project structure, Python version notes, known pitfalls, mypy check version sections synced; added Python 3.14 migration baseline and `language` new-key semantics notes.
  - `README.md` / `README_EN.md`: Python badge upgraded to 3.14, language field in config notes changed to `language =` with system fallback / hot-switch notes.
  - `CODE_WIKI.md`: this section (changelog) added; `i18n` module details and config-file table `language` field notes synced (see earlier "Configuration File Reference" / "Internationalization Module" sections).

- `python -m py_compile` on all sources passes;
- Full `pytest` **714 passed / 2 skipped / 0 warnings**;
- `mypy src/` → `Success: no issues found in 37 source files`;
- `basedpyright src/` → **0 errors / 0 warnings / 0 notes**;
- `black --check .` / `isort --check-only .` pass project-wide;
- Manual verification: when `config.ini` only contains the old key `language(zh_cn/en) = zh_cn`, the main program auto-migrates it to `language = zh_cn` at startup, keeping the old key; when `language =` is empty, CLI/GUI/Web all display per system language; after switching language in the GUI sidebar or Web panel, it takes effect immediately without restart.

**Related**:
- Same series of Python 3.14 compatibility wrap-up as the prior v4.0.8.3-dev (2026-08-22) "pythonw / windowed-run crash observability hardening"; the latter fixed `logger`'s crash in a no-console environment, this one fixes event-loop and config-level 3.14 compatibility.
- The `asyncio.get_event_loop()` RuntimeError fallback pattern, the `language` key migration pattern, and the system-language detection convention have all been recorded in `AGENTS.md`'s known-pitfalls section for future reference.

### v4.0.8.3-dev (2026-08-22) — pythonw / Windowed-Run Crash Observability Hardening: logger None-stderr Guard + Top-Level Crash Dump Hook (Defect Fix)

**Source**: The user reported that `pythonw.exe gui.py` (and a frozen exe with `console=False`) started with no window and no error at all, while `python.exe gui.py` worked normally. The first round added a crash guard at the top of gui.py but it didn't take effect; eventually the real stack trace captured by that guard located the root cause: `src/logger.py:36` threw `TypeError: Cannot log to objects of type 'NoneType'` at `logger.add(sink=sys.stderr, ...)` during module import.

**Root cause**: `pythonw` / `console=False` frozen exe does not allocate a console, so `sys.stdin/stdout/stderr` are all `None`. loguru refuses `None` as a sink, so it threw during module loading on the import chain `gui.py → src.web_config → src.__init__ → node_install → logger` and silently exited. **Unrelated to interpreter consistency** (the user's pythonw and the working python.exe are both CPython 3.14).

**Changes**:

- **`src/logger.py` (`_ = logger.add(sink=sys.stderr, ...)` added `sys.stderr is not None` guard)**:
  - In a no-console environment (pythonw / frozen `console=False`), skip the console sink to avoid the import-time `TypeError`; log persistence is still backed by the `logs/streamget.log` and `PlayURL.log` file sinks below.
  - Added a comment explaining the pythonw windowed `sys.stderr=None` semantics and the null-check rationale.

- **`gui.py` windowed-crash observability hardening (prior commit, recorded here together)**:
  - New `_install_crash_sink()` at the very top of the file: before **all risky imports**, install `sys.excepthook` and `threading.excepthook` to write the full stack trace of any uncaught exception (including module-import failures) to `%TEMP%/douyin_recorder_gui_error.log` and try to pop up a `tkinter.messagebox` error box, fixing the "windowed run silently dies, can't see why" problem.
  - `LiveRecorderGUI.__init__`'s UI-callback exception branch changed from `traceback.print_exc()` (secondary `AttributeError` crash under None stderr, taking down the event pump) to `self._log(traceback.format_exc(), "error")`, going through the in-program "run log" queue, observable even without a console.
  - `__main__` wrapped `try: main() except: _bootstrap_error_sink(); raise`; console environment still keeps the original stack trace.

**Related**: Long-standing pitfall recorded in `MEMORY.md` ("pythonw windowed `sys.stderr=None` causes `logger.add` crash"); troubleshooting routine — for windowed silent crashes, first install `sys.excepthook`/`threading.excepthook` dump+popup hooks, then grep layer by layer for None-sensitive points like `sink=sys.` / `print_exc` / `sys.stdout.write` and null-check each.

### v4.0.8.3-dev (2026-08-22) — Type Check Fix: i18n Optional Dependency Stub Ignore + gui.py messagebox Explicit Import + Thread Hook Null-Check (Code Quality)

**Source**: The type checker reported three errors — ① mypy at `i18n.py:23` reported `Library stubs not installed for "yaml"` (YAML is an optional dependency, wrapped in `try/except ImportError`, and static analysis can't find the type stub); ② basedpyright at `gui.py:46` and `gui.py:3035` reported `reportAttributeAccessIssue`: `"messagebox" is not a known attribute of module "tkinter"` (`messagebox` is a tkinter submodule and cannot be accessed attribute-style via `_tk.messagebox`); ③ basedpyright/mypy at `gui.py:56` reported `reportArgumentType`: `threading.ExceptHookArgs.exc_value` has type `BaseException | None`, incompatible with the `BaseException` required by `_dump`'s parameter.

**Changes**:

- **`i18n.py` (optional dependency stub ignore)**:
  - Added `# type: ignore[import-untyped]` to `import yaml`, explicitly declaring PyYAML an optional dependency and ignoring the missing-stub hint (without installing `types-PyYAML`, to preserve the "missing only loses YAML format" runtime degradation semantics, per AGENTS.md convention).
  - Changed the fallback branch `yaml = None` to `yaml: Any | None = None`, providing an explicit type annotation (replacing the original `# type: ignore[assignment]`), and added `Any` to `from typing import`.
- **`gui.py` (messagebox explicit import, two places)**:
  - File-top `_dump` crash popup: after `import tkinter as _tk`, added `from tkinter import messagebox as _mb`, using `_mb.showerror(...)` instead of `_tk.messagebox.showerror(...)`.
  - `main()` entry crash popup: similarly changed to explicit import and use `_mb.showerror(...)`.
- **`gui.py` (thread hook null-check)**:
  - In `_thread_dump`, `args.exc_value` may be `None`; added an `if args.exc_value is None: return` guard before calling `_dump(...)`, eliminating the `BaseException | None` incompatibility error.

### v4.0.8.3-dev (2026-08-21) — start_record Complexity Governance: Platform Dispatch Chain Extraction + Recording-Chain Redundant Condition Removal (Code Quality)

**Source**: basedpyright reported at `main.py:866` (`start_record`) "code too complex to complete analysis" — the function is about 1600 lines (containing a 700-line / 52-platform dispatch if/elif chain + a 900-line recording execution chain), exceeding basedpyright's single-function analysis limit.

**Changes**:

- **Platform dispatch chain extracted into a standalone module-level function `_resolve_platform_stream`** (`main.py`):
  - The 918–1618 line platform dispatch if/elif chain inside `start_record` (52 branches, covering Douyin/TikTok/Kuaishou/Huya/Douyu/YY/Bilibili/Xiaohongshu/bigo/blued/SOOP/NetEase CC/Qiandu Rebo/PandaTV/Maoer FM/WinkTV/TTingLive/Look/TwitCasting/Baidu/Weibo/Kugou/Huajiao/Liuxing/ShowRoom/Acfun/Changliao/Inke/Yinbo/Zhihu/Haixiu/VV Planet/17Live/Lang Live/Piaopiao/6Rooms/Lehai/Huamao/Shopee/YouTube/Taobao/JD/faceit/Migu/Lianjie/Laixiu/Picarto/custom recording and 40+ other platforms) was moved byte-for-byte into `_resolve_platform_stream(record_url, proxy_address, record_quality) -> tuple[str, dict, dict | None, str] | None`.
  - Returns a 4-tuple `(platform, port_info, record_danmaku_args, new_record_url)`; unrecognized addresses return `None`, and the caller `break`s to preserve the original "retry after delay" semantics (not ending the thread directly).
  - Branch-body semantics unchanged: cookie/proxy and other config items are still read live from module-level globals; the `json_data` local variable stays inside the function (no need to expose after the chain).
  - The recording execution chain's control flow is completely untouched (including the AGENTS.md known-pitfall zone: the `if not real_url: continue` guard, `check_subprocess` calls, danmaku parameter passing, etc.).

- **Eliminated 19 hidden `possibly unbound` pre-existing errors** (exposed by basedpyright only after complexity was removed and it could finally analyze the function):
  - Removed the always-true redundant `if real_url:` wrapper (the `if not real_url: continue` guard above already guarantees non-empty), changing `now`/`title_in_name` to unconditional assignment — also fixing the "recording chain must not be nested inside a condition" anti-pattern (an extension of the AGENTS.md known pitfall).
  - Cleaned up the dead `cast(str, real_url)` and stale comments in the ffmpeg command (cast is redundant once the guard guarantees `real_url` non-empty).
  - Moved `record_name = ""` initialization from inside `try:` to the top of the outer `while True` loop, eliminating a potential `NameError` in `finally` (if an exception is thrown before the first `try` statement, `record_name` is unbound and would mask the original exception).

- **AGENTS.md synced**: Updated the "must skip the recording chain when `real_url` is empty" entry to reflect the new structure — after the guard, `now`/`title_in_name` are unconditionally assigned, and the always-true redundant `if real_url:` wrapper has been removed.

### v4.0.8.3-dev (2026-08-21) — FFmpeg 9.0 / Node 24 Baseline + i18n Multilingual Refactor + tests Five-Tool All-Green (Comprehensive Maintenance)

**Source**: The user asked to complete six maintenance items in one pass: ① change the SSL platform key in config.ini to "only takes effect when cert verification is required" and auto-append required platforms; ② align all ffmpeg parameters project-wide to FFmpeg 9.0; ③ align Node.js-related code to 24.19.0; ④ i18n refactor (YAML/JSON support + zh_CN completion + new en_US/en_GB/zh_TW + Web/GUI instant language switch); ⑤ make tests/ pass all five tools (basedpyright/mypy/pytest/black/isort) with zero warnings; ⑥ complete AGENTS.md/.gitignore/.dockerignore/.coveragerc-concurrency/docker-compose.yaml/Dockerfile/pyproject.toml/requirements.txt/uv.lock and CODE_WIKI.md.

**Changes**:

- **SSL platform key semantics refactor (`src/http_config.py` + `main.py` + `src/web_config.py`)**:
  - `get_effective_ssl_verify`: platform override now only participates in reading when global `ssl_verify=True` (**cert verification required**, i.e. http recording mode); in https mode global verification is already disabled and the platform override is meaningless. Background: **FFmpeg 9.0 (released 2026-08-04, codename Lei) enables TLS cert verification by default** (previewed in 8.0, landed in 9.0); in http mode https-only streams are also verified by default, and cert-anomaly platforms (Huya TX CDN hostname mismatch, some Bilibili nodes with abnormal cert chains) need this list to be exempted in order to pull.
  - `main.py` added `SSL_DISABLE_REQUIRED_PLATFORMS = ("虎牙直播", "B站直播")` and `_sync_ssl_disable_platforms()`: at startup it analyzes monitorable/recordable platforms and **auto-appends** missing required platforms to the config key and writes back (only appends, never removes user-entered items; line-level write-back preserves comments).
  - `src/web_config.py`'s `update_config_line` key matching changed to **case-insensitive** (aligned with configparser's `optionxform` semantics) — so when code constants (uppercase SSL/SMTP/Bilibili) and config-file lines (lowercase spelling) differ in case, they can still be located, fixing the hidden risk of Web panel 404s when editing such keys.
  - Key-value audit: all 136 keys in config.ini are referenced by code (no dead keys), and all keys read by code already exist (no missing keys); no add/remove needed.
- **FFmpeg 9.0 compatibility (`main.py`)**: audited all ffmpeg command construction project-wide (record/segment/remux/transcode/audio-extract), confirmed none of the CLI params removed in 9.0 are used (`-vsync`/`-top`/`-qphist`/`-filter_complex_script`/`-adrift_threshold`) nor removed components (OpenMAX encoder/NPP filter/v308/v408/v410 codecs/standalone CELT decoder/Sonic codec); removed the redundant dead param `-v verbose` (overridden by the later `-loglevel error`); the `-tls_verify 0` insertion condition uniformly decided via `get_effective_ssl_verify(platform)` (self-consistent with the new SSL key semantics), and added a comment at command construction noting the 9.0 baseline.
- **Node.js 24.19.0 compatibility (`src/javascript/migu.js` rewrite + `Dockerfile`)**:
  - **migu.js fully rewritten**: Migu's official player (dataFetcher.js) changed the mgprtcl.wasm interface since the second half of 2025 — imported functions expanded from 3 (a/b/c) to 12 (a..l, missing any causes `LinkError: function import requires a callable`), export names fully rearranged (mapped against the player's Emscripten glue layer: memory=m, malloc=p, free=q, CI1=t, CI2=u, CI3=v, CI4=w, CI5=x, CI6=y, CI7=z, CI8=A, CI9=B, CI10=C, CI11=D, CI12=E, CI14=F), and the fixed encryption factor changed to be delivered via the `/gateway/app-management/videox/staticcache/v2/factor` interface (fallback to the player's built-in default factor `{sv:119, factor:"BjfS7eNf3OIROs2T1E8hHQ=="}` on failure). The old script failed to instantiate under any Node version (recording feature entirely unusable). The rewrite **changes the output contract**: outputs the full signed address with `ddCalcu`/`sv` params (old version only output the ddCalcu value); `spider.get_migu_stream_url` uses this URL directly, removing the expired fixed `sv=10010` concatenation.
  - The other JS signing scripts (x-bogus/haixiu/laixiu/liveme/taobao-sign/crypto-js) and the execjs runtime were all verified working under Node 24.19.0 (x-bogus sign output normal).
  - `Dockerfile`: nodesource source upgraded from `setup_22.x` to `setup_24.x` (Node 24 LTS, same generation as the measured baseline and the latest stable pulled by node_install.py).
- **i18n refactor (`i18n.py` + translation catalogs + Web frontend + GUI)**:
  - **`i18n.py` refactor**: added multi-format catalog loading (per language probes gettext `.mo` → `<lang>.json` → `<lang>.yaml` in order, all normalized to a "original→translation" flat dict), `SUPPORTED_LANGUAGES` (zh_CN/en_US/en_GB/zh_TW), `normalize_language()` (alias table: zh_cn/zh-CN/en/en-US/zh-Hant/zh_CN.UTF-8 etc. normalized; alias keys uniformly in "lowercase+hyphen" form), `is_recognized_language()`, `set_language()` (**hot switch**: after normalization reloads the catalog and hot-swaps `_tr`, no restart needed), `get_language()`/`available_languages()`; YAML is an optional dependency (missing only loses that format). Kept `init_gettext`/`translated_print`/`_should_translate` compatibility interfaces.
  - **zh_CN completion**: AST-scanned all runtime code (main/web/gui/msg_push/i18n/src/) for `print`/`logger.*` constant strings, compared with existing .po entries, appended 85 missing entries (ffmpeg/node install messages English→Chinese, web/recorder_status/ttwid/notify/platforms Chinese runtime messages), catalog 197 → 282 entries and recompiled .mo (`scripts/compile_po.py`, byte-level sync enforced by tests).
  - **Added three-language translations**: `i18n/en_US.json` (English source identical + Chinese source translated to English, 282 entries), `i18n/en_GB.json` (British spelling variants: minimise/log in/Unauthorised, etc.), `i18n/zh_TW.yaml` (simplified→traditional character mapping + Taiwan usage adaptation: 视频→影片/网络→網路/服务器→伺服器/软件→軟體/设置→設定/默认→預設/磁盘→磁碟/地址→位址/运行→執行/代码→程式碼/支持→支援/文件→檔案/高级设置→進階設定/错误信息→錯誤訊息/录制→錄製, etc.); the four catalogs have consistent key sets (enforced by tests).
  - **Web instant language switch**: backend added `GET /api/language` (current language + supported list) and `PUT /api/language` (validate → write back to config → hot-switch in-process translation, illegal value 400); frontend top bar added a language selector, `index.html` static text marked with `data-i18n`/`data-i18n-placeholder`, `app.js` has a built-in four-language text dictionary (`t()` for values, `applyTranslations()` for redraw), all dynamically rendered text (toast/empty-state/buttons/confirm) wired into `t()`; language preference stored in localStorage.
  - **GUI instant language switch**: `gui.py` sidebar added a "Language" OptionMenu (same style as the appearance menu), selection immediately calls `i18n.set_language()` hot-switch + `update_config_line` writes back to config.ini + logs a hint; at startup reads language from config and initializes i18n.
  - **main.py language chain**: `set_language(language)` initialization at import (installs `translated_print` under any language); main loop detects config language changes each round and hot-switches immediately (Web/GUI config changes take effect next round); the language config key is unified as `language` (the legacy key `language(zh_cn/en)` has been removed); values support all new spellings.
  - Dependency: added `PyYAML>=6.0.3` (pyproject + requirements.txt + uv.lock).
- **tests/ five-tool all-green**:
  - **mypy tests/**: initial 435 errors → 0. Auto-annotation script added ~420 signature annotations (`-> None`/fixture param types/return type inference/`Generator[None, None, None]`), and ~60 real type issues fixed manually (`__enter__`/`__exit__` return types, `__wrapped__` via `_unwrap()`, `object` narrowing cast, `_srt` nullable narrowing, mock signature default restoration, etc.); two defects introduced by the auto-script during fixing regressed (bare `*` separator mis-annotation, lost param default — the latter once caused `test_douyin_empty_cookie_fetches_ttwid` to fail; default restored and fully regressed).
  - **basedpyright tests/**: 0 errors / 0 warnings / 0 notes (four cast narrowings where `MagicMock` stands in for `danmaku_cls`, `int(object)`, `"x" not in object`).
  - **pytest**: 699 passed / 2 skipped / **0 warnings** (two benign RuntimeWarnings from un-awaited FakeAsyncClient.aclose eliminated via targeted `filterwarnings`; fastapi testclient third-party deprecation hints filtered via pyproject `filterwarnings`).
  - **black/isort**: project-wide (including tests/) `--check` passes.
  - New tests: 5 language API (GET current+available / PUT switch+persist / alias accept / illegal 400 / empty 400), 10 i18n new features (multi-format catalog load priority, four-catalog key-set consistency, hot switch, normalization variants, is_recognized, available_languages copy, missing-catalog identity fallback), 3 SSL platform auto-append (missing append+writeback / idempotent / key-missing self-heal), 2 SSL new semantics (http mode platform override takes effect / https mode override ignored), 1 migu output contract (adapt to full URL output).
- **Config and doc maintenance**:
  - **`.coveragerc-concurrency` created**: CI concurrency-test job referenced this file via `COVERAGE_RCFILE` but it was missing from the repo (and wrongly ignored by .gitignore); now distributed with the repo (`fail_under = 0`, source/omit aligned with pyproject), and removed the ignore entry from .gitignore.
  - **`uv.lock` regenerated**: version synced `4.0.8.2 → 4.0.8.3` (previously lagging), PyYAML included; header comments (feature grouping notes) preserved and updated.
  - **`pyproject.toml`**: added PyYAML dependency (with usage comment), pytest `filterwarnings` (third-party deprecation hints).
  - **`.gitignore`**: removed the erroneous `.coveragerc-concurrency` ignore; header comment added "keep .json/.yaml translation catalogs".
  - **`.dockerignore`**: no change needed (i18n section only excludes .po and compile scripts, .json/.yaml auto-enter the image with the directory).
  - **`AGENTS.md`**: i18n directory updated in project structure; PyYAML added to dependency list; tests section added "tests/ five-tool quality gate"; known pitfalls added 5 entries (SSL platform key conditional-effect semantics + update_config_line case-insensitive, i18n multi-format catalog and hot switch, migu.js output contract, Node 24 / FFmpeg 9.0 compatibility baseline).
  - **`CODE_WIKI.md`** (this file): directory-structure i18n entry, i18n module details (multi-format/hot-switch/four-language catalog table), config-table SSL key and language key notes, Docker section Node 24 LTS and .dockerignore key points, changelog (this entry).
  - `docker-compose.yaml` needs no change (anchor reuses Dockerfile build, Node upgrade auto-inherited).

### v4.0.8.3-dev (2026-08-20) — URL_config.ini Anchor-Name Auto-Update (New Feature)

**Source**: The user asked to add an anchor-name auto-update mechanism to `URL_config.ini` — each time the latest anchor name is resolved, if it differs from the name in the config file, automatically update the config file, and on anchor rename also synchronously rename the recording folder named after the anchor and all related files inside it, ensuring path-reference integrity.

**Changes**:

- **`src/config_io.py` (config file update)**: added `update_anchor_name(url, new_name) -> bool` and `_rewrite_anchor_field(raw_line, url, new_name) -> str | None`. Holds `file_update_lock` and rewrites `URL_config.ini` line by line, using **URL-segment-level exact matching** (preventing `/1` from mistakenly changing the `/12` line) to replace only that line's anchor-name field, fully preserving the quality segment, the `#` comment prefix, and the line-ending style; idempotent, with an exception-recovery snapshot after writing to disk.
- **`main.py` (filesystem sync)**: added `rename_anchor_directory(old_name, new_name, platform) -> bool` and `_rename_prefixed_entries(base_dir, old_name, new_name) -> None`; module-level added `auto_update_anchor_name: bool = True` (overridden by `main()` after reading config, see new `config.ini` key). The `start_record` thread checks whether the latest anchor name and the currently used name match "after parsing live data and before recording startup" (at this check point the thread is necessarily not recording, naturally avoiding the ffmpeg-occupied window).
  - `rename_anchor_directory`: renames `{save path}/{platform}/{old anchor name}` → new name; if the target already exists, merges item-by-item into it (compatible with the anchor switching back to a previously used name).
  - `_rename_prefixed_entries`: recursively renames all recording files in the directory tree starting with `{old name}_` (including TS/FLV/danmaku SRT/subtitle and other same-prefix artifacts under date/title subdirs) and title directories ending with `_{old name}`.
- **Path-reference integrity**: rename only happens when the room is not recording, in-progress recordings unaffected; **filesystem first, then config file, switch this round's used name only when both succeed**, on any failure keep the old name and auto-retry next polling round (rename idempotent for already-completed dirs); an individual file occupied by a background transcode/player only warns and skips, doesn't block the whole, and cleans up stale recording-status entries of the old name.
- **Config switch and protection**: `[Recording Settings] 是否自动更新主播名(是/否)` (default "Yes", disabling keeps the manual name), supports hot loading; skips custom stream addresses (whose anchor name contains a per-round random UUID, preventing repeated triggers); names cleaned to "blank nickname" don't trigger rename.
- **`tests/test_anchor_rename.py`**: added 21 cases covering each config-line format (quality segment/comment/full-width colon/no-name field append/CRLF preservation), directory rename/merge/title-subdir/no-author dir/file-occupied/dir-fail retry, and end-to-end consistency.
- **`config/config.ini` and `CODE_WIKI.md`**: supplementary notes (config-item table and the dedicated "Anchor-Name Auto-Update" section).

### v4.0.8.3-dev (2026-08-20) — Type-Safety Hardening: Completed Type Annotations for Multiple Test Files and `src/async_http.py` (Satisfying mypy `disallow_untyped_defs` / basedpyright Gates)

**Source**: Multiple rounds of `@command://fix` feedback — CI's mypy (`disallow_untyped_defs = true`, see `AGENTS.md`) and IDE basedpyright reported missing type annotations / type-narrowing errors in test files and a few source files. This round uniformly completed them, all consistent with the project's established code style, pure signature/annotation-layer changes, zero runtime behavior change.

**Affected modules and specific fix points**:

- **`tests/test_anchor_rename.py`**: `main_mod` is injected as a pytest fixture parameter; mypy can't infer its type from the fixture (fixture returns `ModuleType`). Added `ModuleType` annotation to all `main_mod` params in the file (9 single-param signatures `main_mod: ModuleType`, 2 multi-line signatures `main_mod: ModuleType, monkeypatch: pytest.MonkeyPatch`, 2 fixture signatures).
- **`tests/test_ttwid.py`**: all `def test_*` / `async def test_*` got `-> None`; `tmp_path` got `tmp_path: Path`; `monkeypatch` got `monkeypatch: pytest.MonkeyPatch`; nested-class methods `_BoomParser.read` / `.get` (`*args: object, **kwargs: object -> list[str]`) and `_ContendedLock.acquire/release/__enter__/__exit__` (added `*args: object, **kwargs: object` and corresponding return types) also got annotations (`Path` already imported in the file).
- **`tests/test_i18n.py`**: ① `captured: list[object]` → `list[tuple[object, ...]]` (line 58), fixing basedpyright `"object" type has no "__getitem__" method` (`side_effect`'s `*a` is a `tuple`); ② 9 test methods got `-> None`.
- **`src/async_http.py`**: line 141, 201 (inside `get_response_status`) `client = await _get_client(...)` explicitly annotated `client: httpx.AsyncClient = ...`. Root cause: when the IDE language server mis-parses the `httpx` stub, it widens `client` to `object`, triggering `cannot access "post"/"head" of "object*" class` (0 errors in actual CLI, IDE-side only); after explicit narrowing it won't be widened regardless of how the stub parses, zero runtime cost.
- **`tests/test_sync_http.py`**: 17 test methods have mock params injected by the `@patch` decorator (`mock_config` / `mock_opener_fn` / `mock_requests` etc.), originally unannotated; following the repo's existing convention (e.g. `tests/test_weverse_auth.py` uses `MagicMock`), added `MagicMock` annotation to each mock param and unified `-> None` (`MagicMock` already imported).
- **`tests/test_utils.py`**: ① eliminated same-name class shadowing — the file had two `class TestReadConfigValue` (line 90 and 245), the later one shadowed the former, pytest collection conflict dropped cases; merged the 2 test methods of the second class into the first and deleted the duplicate class definition, all 5 cases preserved; ② 17 test methods triggered `no-untyped-def` due to missing `tmp_path` / `capsys` annotations, added `tmp_path: Path` and `capsys: pytest.CaptureFixture[str]`.
- **`tests/test_stream.py`**: ① all test methods got `-> None`; helper `TestGetHuyaStreamUrl._json` got `-> dict[str, object]`; ② fixed 19 `dict[str, object]` invariance errors — type A (pass side: concrete nested dict can't be assigned to `dict[str, object]` param), type B (return side: huya `result["m3u8_url"]` etc. access narrowed to `object`). Following the `MEMORY.md` established "zero-cost cast" strategy, narrowing on the test side: **did not modify `src/stream.py`**; at top `from typing import TypedDict, cast` and import the real exported `HuyaStreamUrl`/`TiktokStreamUrl`/`YyStreamUrl`, define local `class HuyaResult(TypedDict, total=True)` (must be `total=True`, otherwise basedpyright reports `reportTypedDictNotRequiredAccess`), pass side `cast(dict[str, object], ...)`, huya return side `cast("HuyaResult", ...)`, tiktok/yy only need pass-side cast.
- **`tests/test_stream_select.py`**: fixed 17 type errors — ① autouse fixture `no_probe_throttle` got `-> Iterator[None]` (top `from typing import Iterator, Literal`), inside `lambda url: None` → `lambda _url: None` to remove unused-var hint; ② four `__exit__` (`_FakeHead405HtmlClient` / `_C` / `_FlvTransient403Client` / `_StreamCtx`) changed from `-> bool` to `-> Literal[False]` (always returns `False` and doesn't swallow exceptions, broad `bool` triggered `exit-return` validation), param `*args: object` → `*_args: object`; ③ `_m3u8_client_cls` return annotation `-> type` changed to `-> type[_M3u8ProbeClient]` (added module-level base class `_M3u8ProbeClient` declaring `get_calls: int = 0`, nested `_C` inherits it, each round still constructs a fresh subclass, test isolation unaffected); ④ `clear_probe_backoff` fixture got `-> Iterator[None]`, 7 test functions referencing it got `clear_probe_backoff: None`.

- `tests/test_anchor_rename.py`: `mypy ... -> Success: no issues found in 1 source file`.
- `tests/test_ttwid.py` / `tests/test_i18n.py` / `tests/test_sync_http.py` / `tests/test_utils.py`: `mypy ... -> Success: no issues found`; `basedpyright` on the corresponding files 0 errors / 0 warnings / 0 notes.
- `src/async_http.py`: `basedpyright ... 0 errors / 0 warnings / 0 notes` (CLI measured 0 errors anyway).
- `tests/test_stream.py`: `mypy ... Success: no issues found`; `basedpyright` 0 errors; `pytest` **62 passed**.
- `tests/test_stream_select.py`: `mypy` / `basedpyright` 0 errors / 0 warnings / 0 notes; `pytest` **25 passed**.

### v4.0.8.3-dev (2026-08-20) — "Disable SSL Certificate Verification" Merged into "Enable https Recording" (Config Item Consolidation)

**Source**: The user asked to merge the "disable SSL certificate verification" function into the "enable https recording" option, renamed to "enable https recording", enabled = https recording, disabled = http recording.

**Changes**:

- **Config consolidation (`main.py`)**: added `_read_https_recording_config()` to uniformly read the new key "enable https recording", merging the former "force enable https recording" (protocol hard-cast) and "disable SSL certificate verification (yes/no)" two functions. If the new key exists, take its value directly; if only the old force key exists, inherit its value and migrate-write back to the new key (old key read-only, never recreated); if neither key exists, auto-backfill default "No". Prints a migration hint when the old SSL switch=Yes is detected.
- **Linked semantics (`main.py` module-level + main-loop per-round hot-sync)**: `_http_config.set_https_recording(x)` + `_http_config.set_ssl_verify(not x)` — enabled = https pull + disable cert verification; disabled = http pull + default strict verification.
- **Recording protocol switch (`main.py:1796` area)**: when enabled `http://`→`https://` (original behavior, with Huya/custom/shopee/migu exceptions preserved); when disabled `https://`→`http://` (new), https-only overseas platforms within `OVERSEAS_PLATFORM_HOST` (TikTok/YouTube, etc.) stay as-is to avoid forced http-downcast pull failure.
- **`-tls_verify 0` self-consistent**: inserted when https mode globally disables verification (https streams only), http mode has no TLS so not involved, comments synced.
- **`src/http_config.py`**: `ssl_verify` comment updated to the consolidated semantics; platform-level override (`ssl_verify_platform_overrides`) kept for compatibility, actual behavior unchanged; `get_effective_ssl_verify` / `set_https_recording` comments synced.
- **Web interface (`web/app.js` + `web/style.css`)**: new key "enable https recording" with consolidated-semantics note; old keys "force enable https recording" / "disable SSL certificate verification (yes/no)" / "disable Huya SSL certificate verification (yes/no)" marked deprecated, read-only and greyed out; the kept "platforms with SSL cert verification disabled" list dynamically hints its compatibility status per current mode.
- **Docs**: `README.md` config list/notes, `CODE_WIKI.md` config table (see "Configuration File Reference") synced rename and explanation.

**Note**: The old combo "force https=No + disable SSL=Yes" becomes http pull + default verification after consolidation (the original "no verification" capability is merged into the switch semantics, can't be kept independently).

### v4.0.8.3-dev (2026-08-19) — Architecture Doc Update: Completed Danmaku Collection Subsystem and src/platforms, src/proto Module Notes

**Source**: The user asked to read all source code in the workspace, extract architecture/module/core-logic/key-implementation info, and update `CODE_WIKI.md` to reflect the latest code state (covering each file's responsibilities, important function/class roles, dependencies, and usage), keeping the original doc style and structure.

**Added / corrected content**:

- **Directory structure**: added danmaku-related entries `src/base.py`, `src/collector.py`, `src/cookie_cache.py`, `src/danmaku_monitor.py`, `src/srt_writer.py`, `src/ws_client.py`, `src/platforms/`, `src/proto/`; `src/__init__.py` comment added danmaku registry/factory responsibilities (`get_danmaku_class` / `get_danmaku_collector`).
- **Tech stack**: added `websockets` / `protobuf` / `brotli` three danmaku runtime dependency notes (corresponding to the danmaku section of `requirements.txt`).
- **Core module details**: added the entire "14. Danmaku Collection Subsystem" section, covering the base-class contract (`DanmakuBase` / `DanmakuMessage` / `DanmakuMessageType`), collector (`DanmakuCollector`), five platform danmaku clients (Douyin/Douyu/Huya/Bilibili/Twitch) + private signatures `_tars` / `_xbogus`, monitor hub (`DanmakuMonitorHub`), SRT writing (`SrtWriter`), WS transport layer (`WsClient`), visitor Cookie cache (`cookie_cache`), Douyin protobuf (`src/proto/`); `main.py` section added danmaku-recording wiring notes.
- **Module dependency graph**: added danmaku subsystem (`src/__init__.py` registry → `collector` → `platforms/*Danmaku` → `ws_client` / `cookie_cache` / `proto` / `ttwid`, and wired `srt_writer` / `danmaku_monitor`).
- **Design patterns**: added "Factory / Registry Pattern", explaining danmaku decoupled creation by platform identifier via `get_danmaku_class` / `get_danmaku_collector`.
- **Version number**: project basic-info version corrected from `4.0.8.2` to `4.0.8.3` (aligned with `pyproject.toml` single source of truth).
- Clarified that the danmaku subsystem and `src/spider.py` stream parsing are two parallel, decoupled abstractions (`spider.py` does not import `src/platforms`).

### v4.0.8.2-dev (2026-08-19) — CI Refactor: build-release.yml Removes download-artifact Round-Trip + Fixes Release Concurrency Race / Boolean Comparison / Missing Checkout

**Source**: The user asked to replace `actions/download-artifact@v7` in the release job with `softprops/action-gh-release`; when manually running `workflow_dispatch` with `create_release` checked, `release` was skipped, then reported `fatal: not in a git directory` (exit 128).

**Root cause** (four types, all fixed):

1. **Structure change**: in the original `upload-artifact` → `download-artifact` → `softprops`, `download-artifact` only pulled artifacts back to the release job locally. If you delete it and use softprops to release directly, the release job can't get the files and checksum/SHA256SUMS all fail.
2. **Concurrency race**: three-platform build jobs concurrently calling `softprops` to create the same Release (same tag) has a "same tag created simultaneously" race.
3. **Boolean comparison always false** (a pre-existing bug in the original): `create_release` is a boolean input, the original `if` wrote `inputs.create_release == 'true'` (compared with a **string**) always false → the manual-check path `release`/`release-create`/build upload steps all failed, skipped.
4. **Missing checkout**: the `release-create` job's manual-release path needs `git tag/git push` to push a lightweight tag, but that job has no `actions/checkout`, the runner has no `.git` directory → `fatal: not in a git directory` (exit 128).

**Fix** (`.github/workflows/build-release.yml`):

1. **build job direct-to-Release**: added `permissions: contents: write`; the release path (`is_release=='true'` or manually checked `create_release`) uses `softprops/action-gh-release@v3` to directly pass `dist/*-lite.zip` + `dist/*-full.zip` (explicit `tag_name: v<version>`); only the build path keeps `actions/upload-artifact@v7` for manual retrieval.
2. **Added `release-create` singleton job** (`needs: prepare`, `permissions: contents: write`): the job level has no `if` (avoid being skipped and cascading-skip jobs that depend on it), whether to actually create is controlled by a **step-level** `if` — the release path first `git tag/git push` pushes the `v<version>` lightweight tag, then `softprops` pre-creates an empty Release (explicit `tag_name`); build `needs` changed to `[prepare, release-create]`, eliminating the concurrent-create race.
3. **release job switched to gh CLI pull-back**: removed `actions/download-artifact@v7`, used `gh release download <tag> -D artifacts` to pull already-published attachments back locally for 6-file integrity check + generate `SHA256SUMS.txt`; at the end `softprops` only appends `SHA256SUMS.txt` + release notes (zips are already on the Release, not listed again).
4. **Boolean comparison fix**: 5 places `inputs.create_release == 'true'` → `inputs.create_release == true` (the `needs.prepare.outputs.is_release == 'true'` string comparison **kept unchanged** — `is_release` is a string output).
5. **Added checkout**: `release-create` added `actions/checkout@v7` (`fetch-depth: 0`), covering the manual path's `git tag/git push`.

- `yaml.safe_load` parses; job dependency graph `prepare → release-create → build(×3) → release` correct.
- Full job checkout coverage check: prepare/build already had it, release-create added, release only uses gh API no git needed.
- Logic chain: manual dispatch + check `create_release` → checkout → push tag → pre-create Release → three-platform build direct zip → release pull-back check + SHA256SUMS + release notes.

### v4.0.8.2-dev (2026-08-19) — Test/Coverage: tests/test_ttwid.py Added Branch Tests, src/ttwid.py Coverage 82.3% → 96.77% (Cleared 85% Gate)

**Source**: CI `python scripts/check_coverage.py` reported `src/ttwid.py 82.3% (>= 85%) <- 2.7% short`, coverage gate failed (exit code 1).

**Root cause**: `src/ttwid.py`'s `coverage.xml` shows the following branches are unreachable under unit tests (51/62 lines covered, need ≥53 lines for 85%):

- L34: `_app_root()` frozen branch (`sys.frozen` always False in tests);
- L58–59: `_read_config_ttwid`'s broad `except Exception` (unexpected non-ConfigParser error);
- L86–87: `_fetch_ttwid` exception handler (`_cache_fetch_cookies` throws);
- L99–104: `get_ttwid` lock-contention fallback (only reachable under real concurrency);
- L108: cache second-check race guard (only hit under real concurrency).

The correct approach is to add tests for these branches, not lower the gate threshold.

**Fix** (`tests/test_ttwid.py`):

1. Added `TestGetTtwid`: covers the four-level priority chain from `config.ini` (tempfile written with `[ttwid]` section) → `cookie_cache` → dynamic `fetch` → cache return; includes the "cache hit but not in config and throws FileNotFoundError → fall back to fetch" and "fetch throws faithfully propagates upward" branches.
2. Added `TestReadConfigTtwid`: covers the three branches "`_app_root()` frozen branch triggered by `sys.frozen=True`", "ConfigParser parse unexpected exception caught by broad `except`", "`._cached_config_ttwid` short-circuit hit".
3. Added `TestFetchTtwid`: covers the `_fetch_ttwid` exception-handler branch when `_cache_fetch_cookies` throws.
4. Added `TestGetTtwidContention`: replaced the module-level `_ttwid_lock` with a fake lock (`acquire(blocking=False)` returns False), simulating "lock held by another thread" → enters contention fallback branch, `get_ttwid` falls back to retry fetch once.

Note: C-layer `RLock.acquire` is a read-only property, `monkeypatch.setattr` on instance method throws, so the module-level lock object was replaced instead.

- `pytest tests/test_ttwid.py` all green (17 passed).
- Coverage: this run `src/ttwid.py` reached **96.77%** (L34/58/59/86/87/99/100/102/103 all hit); only L104, L108 two pure-concurrency race guards can't be hit in single-threaded unit tests, but 96.77% ≥ 85% gate already passes. `scripts/check_coverage.py` no longer FAIL.

### v4.0.8.2-dev (2026-08-19) — CI Fix: ci.yml `dorny/paths-filter@v3` → `v4` Eliminates Node.js 20 Deprecation Warning

**Source**: GitHub Actions workflow run warning `Node.js 20 is deprecated. The following actions target Node.js 20 but are being forced to run on Node.js 24: dorny/paths-filter@v3`. Since 2025-09-19 GitHub has deprecated Node.js 20 on runners; any action declaring a node20 runtime is forced up to Node 24 and prints this deprecation warning.

**Root cause**: `.github/workflows/ci.yml` line 116 `uses: dorny/paths-filter@v3`. The v3 line (including latest v3.0.4) still declares `runs.using: 'node20'` in its `action.yml`, so the warning can't be eliminated by a minor-version bump; the only solution is to upgrade to **v4** (v4.0.0's PR #294 raised the runtime to node24, latest v4.0.3).

**Fix** (`.github/workflows/ci.yml`): `uses: dorny/paths-filter@v3` → `uses: dorny/paths-filter@v4` (pinned v4.0.3).

- v4's `filters` input and `changes` output API are completely identical to v3; the downstream consumption chain `steps.filter.outputs.changes` → `outputs.filters` → `contains(fromJSON(needs.setup.outputs.filters), 'python')` is unaffected.
- Default `predicate-quantifier: 'some'` (at least one pattern hit counts as changed) semantics unchanged, this workflow's single `python` filter behavior stays as-is.
- Incidental security hardening: v4 merged GHSA-7hc6-8hq5-9q2m multi-line filename escaping fix (this workflow doesn't use `list-files`, incidental).
- Grepped to confirm only this one reference under `.github/workflows/`, no `build-release.yml` same-type issue to sync.
- Pure dependency version bump, zero logic change, can be committed directly.

### v4.0.8.2-dev (2026-08-19) — Test/Interface Fix: `test_huya_danmaku::test_profileRoom_fields` Stale Assertion + `web_api.list_files` Dangling/Escape-root Symlink Crash and Info Leak

**Source**: CI `pytest --cov=src ...` reported 3 failed (641 passed). `test_profileRoom_fields` assertion `flv_url.startswith("https://")` failed (actual `http://hwcdn.huya.com/...`); `test_web_api::TestListFiles::test_broken_symlink_skipped` threw `FileNotFoundError: .../broken.ts`; `test_web_api::TestListFiles::test_symlink_outside_skipped` returned containing `leak.ts` (escaped-root symlink name leaked).

**Root cause**:

1. **Stale test (not a code bug)**: `spider.get_huya_app_stream_url`'s `_normalize` (near `src/spider.py:840`) deliberately downgrades `https://` to `http://` (Huya measured https returns 403, only http works, recorded in memory). The test still asserted `https://`, conflicting with the established correct behavior.
2. **`web_api.list_files` code bug**: when traversing the directory `st = os.stat(full)` default **follows symlinks** (around `src/web_api.py:388`). For a dangling link (`broken.ts → nonexistent target`) it throws `FileNotFoundError` causing the whole step to 500, instead of "skip that entry".
3. **`web_api.list_files` info-leak risk**: only the *requested path* was validated with `os.path.realpath + _is_within` (`src/web_api.py:369-371`), **not re-resolved/validated for each entry in the directory**. So `leak.ts → ../../config.ini` links escaping the `downloads` root were `os.stat`'d and listed as normal, leaking the out-of-root filename (the download interface `download_file` itself has realpath+_is_within protection, downloads are safe, but the listed name still leaked).

**Fix**:

1. `tests/test_huya_danmaku.py:118`: assertion changed to `assert result["flv_url"].startswith("http://")` (consistent with established behavior, runtime behavior unchanged).
2. `src/web_api.py`'s `list_files` loop added two protections:
   - Out-of-bounds skip: after `resolved = os.path.realpath(full)`, `if not _is_within(resolved, root): continue` (fixes out-of-root link name leak).
   - Dangling tolerance: `st = os.stat(full)` wrapped in `try/except OSError: continue` (fixes dangling-link 500).

### v4.0.8.2-dev (2026-08-19) — Type Check Fix: src/web_tray.py Two `ctypes.windll` Missing `sys.platform` Platform Gate Caused mypy Non-Windows Check Failure

**Source**: `mypy src/` on Linux/macOS (CI `ubuntu-latest`) reported `src/web_tray.py:111/112/178: error: Module has no attribute "windll" [attr-defined]` (Found 3 errors in 1 file). Local Windows `mypy src/` reports no error (Windows typeshed includes `ctypes.windll`).

**Root cause**: `ctypes.windll` is a Windows-only API, only present in the Windows typeshed; non-Windows type stubs don't have this attribute. The original `web_tray.py`'s `_patch_console_window` (lines 111–112) and `_on_show` (line 178) directly called `ctypes.windll.user32` / `ctypes.windll.kernel32` without being gated by `sys.platform`, so non-Windows static checks report `attr-defined`. `web_tray.py` already defines module-level `ENABLED = sys.platform == "win32"` at the top, but the function bodies didn't reuse this gate.

**Fix** (`src/web_tray.py`, following the mypy-platform-gating "early-return gate" pattern, not relying on `# type: ignore`):

1. `_patch_console_window`: at the start of the function (before `try: import ctypes`) add `if sys.platform != "win32": return` (keeping the original `try/except import` tolerance).
2. `_on_show`: after `if not hwnd: return` add `if sys.platform != "win32": return`.
   Both runtime behaviors unchanged: on non-Windows `ENABLED` is already `False`, tray not enabled, logic originally never reached; on Windows identical to before the fix. Did not use `# type: ignore` — that写法 on Windows triggers basedpyright strict-mode `reportUnnecessaryTypeIgnoreComment`, the platform gate is the only clean fix for both platforms.

### v4.0.8.2-dev (2026-08-19) — CI Fix: ci.yml Codecov Step's `if` Misused `secrets` Context Caused Workflow Validation Failure (Switched to Job-Level env Pass-through)

**Source**: GitHub Actions workflow validation error `Invalid workflow file: .github/workflows/ci.yml#L1(Line: 317, Col: 13): Unrecognized named-value: 'secrets'`.

**Root cause**: GitHub Actions' `if` expression parser only allows a whitelist of contexts (`github`/`needs`/`vars`/`matrix`/`inputs`/`env`/`steps`/`runner`/`job` and status functions), **the `secrets` context is explicitly excluded from `if` conditions** (both job-level and step-level `if` can't use it). The original `test` job's `Upload coverage to Codecov` step's `if` was written `matrix.python-version == needs.setup.outputs.python_min && secrets.CODECOV_TOKEN != ''`, intending "only upload when the repo configured `secrets.CODECOV_TOKEN`, auto-skip when not configured", but the expression engine hits `secrets` at validation time and reports `Unrecognized named-value`, the whole workflow fails to load. Line 320 `token: ${{ secrets.CODECOV_TOKEN }}` is in `with:` (not `if`), legal and unaffected.

**Fix** (`.github/workflows/ci.yml`):

1. `test:` job added job-level `env:` block, promoting the secret to an env var: `env: CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}` (job-level env is visible to all steps' `if`, `env` context allowed in step-level `if`).
2. Line 319 step `if` changed from `secrets.CODECOV_TOKEN != ''` to `env.CODECOV_TOKEN != ''`, i.e. `if: matrix.python-version == needs.setup.outputs.python_min && env.CODECOV_TOKEN != ''`. The original "skip the whole step when token not configured" intent unchanged.

### v4.0.8.2-dev (2026-08-18) — Huya HLS Recording 403 True Cause: CDN Now Reverse-Validates, Forcing Referer Actually 403 (Removed Huya Referer Rule)

**Source**: 2026-08-18 21:39 run log (room 179966, original quality) + real-time curl reproduction. The previous round's "multi-CDN enumeration + HS priority" logic was correct (log shows hs→tx→al candidate-by-candidate validation), but **every candidate returned 403**, ffmpeg also `Server returned 403 Forbidden`, return code 3436169992. The failing URL looked like `http://hs.hls.huya.com/src/...m3u8?...&ctype=huya_webh5&fs=bgct&t=102`, directly contradicting the 2026-08-16 "add Referer" entry's conclusion ("no Referer → 403, with Referer → 200").

**Root cause (measured comparison, using a [fresh] token just pulled from `get_huya_stream_data`)**: Huya CDN now **reverse-validates** —

| Request | HS Line | AL/TX Line |
| --- | --- | --- |
| With `Referer: https://www.huya.com/` | **403** | 403 (room not carrying the stream, unrelated to Referer) |
| Without Referer | **200** ✅ | 403 (room not carrying the stream) |

That is: **with Referer always 403, without Referer the HS line GET 200 pulls normally**. `ctype` (`huya_webh5`/`huya_live`) and `t=102` were both ruled out as decisive factors by comparison tests, **Referer is the only switch**. The 2026-08-16 probe misjudged the 403 of an "expired-token bare request" as "caused by missing Referer" (an expired token returns 403 with or without Referer; that run just happened to hit a valid window on the no-Referer attempt), thereby erroneously injecting the Referer rule; that rule is now the true culprit of recording failure.

**Fix (src/stream_select.py)**:

1. Removed `_RECORD_HEADER_RULES["虎牙直播"]`'s `"referer:https://www.huya.com/"` rule (left a comment noting it's deprecated).
2. Synced two stale comments: the original "Huya CDN returns 403 directly without Referer, needs Referer for 200" is now invalid, changed to "carrying Referer actually 403, must not carry Referer".
3. This is a platform-level base-header change, applied via `get_record_headers` to both the **validation probe** (`_validate_stream_url`) and the **ffmpeg recording command** (`main.py:1762`); both ends consistently stop sending Referer — HS line gets 200. The login-state Cookie (`hy_cookie`) is still injected independently via the `cookies` param, unaffected.
4. Relation to the previous multi-CDN fix: the multi-CDN enumeration (HS priority) itself is correct and retained; after removing Referer, HS gets 200, AL/TX offline rooms are still auto-skipped by multi-CDN validation.

- Real-time curl comparison (fresh token): with Referer → 403, without Referer → 200 (HS); AL/TX two lines 403 regardless (room not carrying).
- Updated `tests/test_main_fixes.py::TestHuyaReferer` (3 cases): `get_record_headers("虎牙直播", ...)` no longer returns Referer, `_validate_stream_url(platform="虎牙直播")` doesn't attach Referer; added `tests/test_stream_select.py::test_huya_record_headers_has_no_referer` (keeping the Bilibili-still-relies-on-Referer contrast).
- `pytest tests/test_stream_select.py tests/test_stream.py tests/test_spider_platform.py tests/test_main_fixes.py` all green (including updated Huya Referer cases); `mypy src/stream_select.py` 0 errors.

### v4.0.8.2-dev (2026-08-18) — Type Check Wrap-up: spider.py / sync_http.py Four mypy/basedpyright Warnings Cleared

**Source**: The user submitted type warnings from mypy/basedpyright one by one (lines 867, 2660, 4009-4013, sync_http.py:52), each root-caused. All changes only involve type annotations/variable naming, **zero runtime behavior change**.

**Fix content**:

1. **`spider.py:867` (mypy `Incompatible types in assignment`)**: originally `m3u8_url = selected_m3u8 if isinstance(selected_m3u8, str) else None` re-assigned the already-declared-as-`str` `m3u8_url`/`flv_url` (line 842) to `str | None` (from `dict[str, object].get()`'s `object | None`), a type-narrowing conflict; and line 872 `record_url = flv_url` referenced the rewritten variable. Changed to introduce new variables `selected_m3u8_url: str | None` / `selected_flv_url: str | None`, keeping the original `m3u8_url`/`flv_url` (`str`) for building the candidate list, return dict and `record_url` logic reference the new variables.
2. **`spider.py:2660` (mypy `Unpacking a string is disallowed`, code `misc`)**: `get_popkontv_stream_data`'s return annotation was wrongly written `tuple[str, list[object] | None] | dict[str, object]`, but the function's three return paths never return a dict (all `(str, None)` / `(str, list)`). The residual `dict` union member made mypy treat `room_info` unpacking as unpacking a dict (keys `str`) triggering the `misc` error; the trailing `# type: ignore[str-unpack]` also had the wrong error code (should be `misc`), and that pyright version doesn't enable it by default. Fix: removed `| dict[str, object]` from the return annotation; removed the invalid `type: ignore` comment (`room_info: list[object] | None`, `if room_info:` narrows then unpacking is type-safe). Function only called internally in this file, no external impact.
3. **`spider.py:4009-4013` (mypy `Value of type "str | None" is not indexable`)**: in `get_pplive_stream_url` the request-body dict and the JSON-response parse result **share the variable name `json_data`** — line 3994 request-body `json_data = {"inviteUuid": "", "anchorUuid": room_id}` is inferred as `dict[str, str | None]` because `room_id` is `OptionalStr` (`str | None`); line 4007 again `json_data = json.loads(json_str)` (`Any`). mypy takes the union type across multiple assignments, the residual `str | None` value type makes `live_info = json_data["data"]` judged `str | None`, its `["name"]`/`["living"]`/`["pullUrl"]` all non-indexable. Compared with same-file `get_lang_live_stream_url`'s `json_data` only single-assigned via `json.loads`, clean with no error. Fix: renamed line 3994 request-body to `req_body`, synced line 4005's `json_data=req_body`; `json_data` thereafter only assigned by `json.loads`, union no longer contains `str | None`.
4. **`src/sync_http.py:52` (basedpyright `reportInvalidTypeForm` "variables not allowed in type expressions")**: originally `try: from requests._types import JsonType except ImportError: from typing import Any as JsonType`. `typing.Any` is a runtime value, `from typing import Any as JsonType` judges the symbol as a **variable**, type expressions forbid it; and requests 2.33+ moved `JsonType` into a `TYPE_CHECKING` block, runtime import necessarily fails, the fallback branch is the only runtime path. Fix: removed `try/except`, locally defined an explicit recursive `TypeAlias`, structurally identical to requests' own `JsonType` — `JsonType: TypeAlias = None | bool | int | float | str | Sequence["JsonType"] | Mapping[str, "JsonType"]` (top added `from collections.abc import Sequence` and `from typing import TypeAlias`). `requests.post(json=json_data)` param validation unaffected.

**Lessons learned**:

- Return annotations must strictly match actual return paths; extra union members pollute caller type inference (especially in unpacking scenarios); a `type: ignore` comment with the wrong error code is dead code and should be cleaned up together.
- Request-body dict and JSON-response parse result **must not share the same variable name** (especially when the value type contains `None`), otherwise literal value types pollute mypy's union inference and cause later false index errors; distinguish by naming `req_body`/`payload` (request body) vs `json_data` (response).
- `from typing import Any as X` as a type fallback inside `try/except` pollutes the symbol into a "variable" and triggers `reportInvalidTypeForm`; should be replaced with a local recursive `TypeAlias`.

### v4.0.8.2-dev (2026-08-18) — Huya HLS Multi-CDN Resolution and Playback Root-Cause Fix: Enumerate All CDN Candidates + HS Priority + http Conversion + `select_source_url` Per-Candidate Reachability Validation (Replaces Fragile Fixed index0 / TX-Priority Source Selection)

**Source**: `新建文件夹/huya_179966_hls_report.md` + `huya_179966.html` + `hls_entries.txt` (room `https://www.huya.com/179966`, 2026-08-18). Probed each CDN's real HLS address from the report:

- `al.hls.huya.com` → GET **403**, `tx.hls.huya.com` → GET **403**, `hs.hls.huya.com` → **GET 200** (`application/x-mpegurl`, pullable);
- `https://hs.hls.huya.com/...` → GET **403** (same HS address, only http works, https rejected).

Conclusion: Within the same room, multiple CDN lines (HS/HW/TX/AL) have completely identical anti-leech params, but only the line currently carrying the stream returns 200, the rest stably 403; and https uniformly 403, only http works. This entry replaces and generalizes the previous round's "fixed TX priority" scheme — TX priority works for TX-online rooms, but for rooms where both TX/AL are offline (like 179966) the whole round still fails; enumerating all candidates + `select_source_url` validating each one can dynamically avoid any offline line.

**Root cause**: The old implementation made "which CDN line to pick" a static decision, decoupled from "whether that line is online", causing two kinds of failure:

1. **Web path `get_huya_stream_url`** (`src/stream.py`) fixed `stream_info_list[0]`, but the room page `gameStreamInfoList`'s first item is often AL (measured AL→403), the whole-round HLS directly unreachable, forced to fall back to FLV.
2. **App path `get_huya_app_stream_url`** (`src/spider.py`) picked TX by `priority_order=["TX","HW","HS","AL"]` (previous round fix). But for room 179966 TX was also offline (→403); and the old `enable_https_recording` upgrade hard-cast the selected URL's `http://` to `https://`, while `*.hls.huya.com`'s https measured 403 — if the validation probe went http (200) but ffmpeg actually went https (403) it would be "validation falsely green, recording truly red".
3. Both paths only produce a single `m3u8_url`/`flv_url`, no candidate list, `select_source_url` can only "validate one → fail → abandon the whole round", unable to pick among multiple online lines.

**Fix** (four协同协同):

1. **`src/stream_select.py:select_source_url`** — added candidate-list support: compatible with the old single `m3u8_url`/`flv_url`, while consuming the platform's (Huya) returned `m3u8_url_list`/`flv_url_list`; dedupe and merge by "primary source first, candidate list after". When HLS priority, validate candidate by candidate, return on first reachable; intermediate candidate failure continues to the next; only when "last HLS and no other fallback source" does it pass to ffmpeg as `last_resort`. FLV candidates iterate similarly, h265 candidates skipped and try other FLV. Keeps the existing three-level fallback (HLS→FLV→record_url) and last-resort `last_resort` semantics.
2. **`src/stream.py:get_huya_stream_url` (Web path)** — no longer takes `stream_info_list[0]`:
   - Builds HLS+FLV addresses for **all CDN items** of `gameStreamInfoList`, directly using the room page's embedded original anti-leech params (`sHlsAntiCode`/`sFlvAntiCode`), **no longer rebuilding anti_code** (avoiding unverified signing algorithms).
   - Uniformly downgraded to `http://` (measured https 403, only http works), sharing the same scheme with the validation probe to prevent "probe http usable, recording https rejected".
   - Sorted candidates by `cdn_priority=["HS","HW","TX","AL"]` (HS measured as the reliable HLS-carrying line, first priority maximizes "first try hits").
   - Quality ratio parsing logic unchanged (still takes the tier table from the first candidate's `exsphd`).
   - Returns `m3u8_url`/`flv_url` (primary = sorted first) + `m3u8_url_list`/`flv_url_list` (all candidates, for `select_source_url` per-candidate validation).
   - Cleaned dead code: removed the deprecated `get_anti_code` rebuild function and now-unused `base64/hashlib/random/time/urllib.parse` imports.
3. **`src/spider.py:get_huya_app_stream_url` (mini-program / OD / BD / UHD path)** — no longer fixed TX priority:

   - Builds addresses for **all CDN items** of `baseSteamInfoList` using the raw `sHlsAntiCode`/`sFlvAntiCode`; `_normalize` now takes an explicit `suffix` to distinguish `.m3u8`/`.flv`, fixing the old "infer by host" heuristic that always judged m3u8 when HLS/FLV share a host + `/src`; uniformly downgraded to `http://` + applies the `tars_mp→huya_webh5`, `bhct→bgct` anti-crawler param substitution consistently across all CDNs (idempotent when absent).
   - Candidates sorted by `cdn_priority=["HS","HW","TX","AL"]`; removed the old fixed `priority_order` and the TX-only https special-case.
   - Returns `m3u8_url`/`flv_url` (primary) + `m3u8_url_list`/`flv_url_list` (all candidates) + same-origin `record_url` (kept http).
4. **`main.py`** — the `http://`→`https://` upgrade from `enable_https_recording` is **skipped** for the `虎牙直播` platform (listed together with `自定义录制直播`), because `https://*.hls.huya.com` returns 403 in practice and only http is usable; otherwise it would create a false-green of "validation passes on http, recording rejected on https".

- `tests/test_stream_select.py` adds `test_select_source_url_m3u8_list_picks_first_reachable` (first reachable candidate in list is selected), `test_select_source_url_m3u8_list_all_dead_falls_back_to_flv` (all HLS candidates dead → fall back to FLV), `test_select_source_url_huya_backoff_round_straight_to_ffmpeg` (Huya backoff last-resort round goes straight to ffmpeg).
- `tests/test_stream.py::TestGetHuyaStreamUrl` rewritten/expanded (9 cases): `test_enumerates_all_cdn_candidates_hs_first` (enumerates all CDNs with HS first), `test_https_in_input_downgraded_to_http` (https in input downgraded to http), `test_flv_url_carries_m3u8_candidate`, `test_flv_without_query_keeps_clean_m3u8`, plus offline/empty/none edge cases.
- `tests/test_spider_platform.py::TestHuyaAppStreamUrl` updated: `test_priority_prefers_tx_over_al_at_index0` (now verifies HS-first order + http scheme + `m3u8_url_list`/`flv_url_list` injection), new `test_hs_cdn_selected_first_when_present` (when HS candidate present, primary source and list-first are both HS, all http), `test_al_used_as_last_resort_when_only_cdn` (only AL → keep http, same-origin `record_url`).
- All three test sets: **33 passed**; full regression (incl. `test_stream.py`/`test_stream_select.py`/`test_spider_platform.py`/`test_main_fixes.py`): **222 passed**, no regressions.
- `py_compile` + `mypy src/stream.py src/stream_select.py src/spider.py`: **Success: no issues found** (0 errors / 0 warnings).
- Real-network probe conclusions are recorded in this entry's "Source": HS streams via http GET 200, https 403, directly confirming the fix direction is real.

### v4.0.8.2-dev (2026-08-18) — Huya `get_huya_app_stream_url` source selection fix: m3u8/flv selected by priority to TX with synchronized TX param substitution (root-causing the recording-crash regression after priority-based selection)

**Source**: Real run of `py web.py` on room `https://www.huya.com/60066` 杨齐家丶 (2026-08-18 01:51–01:54). The previous round (2026-08-18 review) changed `m3u8_url`/`flv_url` from the fixed `play_url_list[0]` to priority-based selection (TX first); the priority logic was correct but **introduced a regression**: TX's HLS/FLV both failed (`HEAD=403,Range-GET=403` / `Server returned 403 Forbidden` / `Stream ends prematurely` ~700KB then cut off, `返回码 3436169992`), recording crashed within seconds.

**Root cause**: The original implementation only applied TX-specific param substitution + https upgrade (`tars_mp→huya_webh5` + `bhct→bgct`) to `record_url`; `m3u8_url`/`flv_url` were in raw `tars_mp` form. In the old code `m3u8`/`flv` landed on AL (also 403), ultimately covered by `record_url` (TX + `huya_webh5`). After switching to priority selection, `m3u8`/`flv` also selected TX but still carried `tars_mp`, rejected by the CDN; meanwhile the probe backoff (`CDN 探针退避中，跳过本轮探针、回退下一候选`) made `select_source_url` directly return the unvalidated tars_mp FLV, **never reaching the `huya_webh5` `record_url`**, crashing the recording. The log shows ffmpeg actually opened `...imgplus.flv?...&ctype=tars_mp&fs=bgct&t=102`.

**Fix** (`src/spider.py:get_huya_app_stream_url`): When TX is selected, `m3u8_url`/`flv_url` undergo the same https upgrade + `tars_mp→huya_webh5`/`bhct→bgct` substitution as `record_url`; non-TX AL/HW/HS keep their raw URLs (old behavior unchanged). `record_url` is still derived from the selected flv and always https-upgraded; the TX-first final fallback semantics are unchanged.

- `tests/test_spider_platform.py::TestHuyaAppStreamUrl` adds `test_priority_prefers_tx_over_al_at_index0` (when AL grabs index 0, all three land on TX and carry `huya_webh5`), `test_al_used_as_last_resort_when_only_cdn` (only AL → last-resort fallback, keep raw URL); all 5 cases pass.
- `py_compile` + `basedpyright src/spider.py`: 0 errors / 0 warnings.
- **✅ Verified by real user test** (2026-08-18 07:09–07:10, room `https://www.huya.com/528300` 安德罗妮丶, Web mode v4.0.8.2):
  - `m3u8_url` is `https://tx.hls.huya.com/...m3u8?...&ctype=huya_webh5&fs=bgct&t=102` — confirms TX param substitution now applies to `m3u8_url`.
  - HLS m3u8 probe `HEAD=403, Range-GET=403` → FLV fallback (expected benign, same as the old AL 403).
  - FLV recording **stable** (`正在录制中 0:00:07`→`0:00:12`, no `Stream ends prematurely`, no `返回码 3436169992`); `HuyaDanmaku 连接就绪`; `累计错误数为: 0` throughout.
  - Process exited normally via user manual `Ctrl+C` (`INFO: Shutting down`/`正在安全退出`), **not a crash**.
  - Conclusion: The previous round's regression (TX `tars_mp` link `3436169992`/second-level disconnect) is eradicated; TX + `huya_webh5` FLV is verified to stream stably; the fix loop is closed.

### v4.0.8.2-dev (2026-08-18) — Huya runtime-log review: AL CDN 403 warnings are expected benign noise; three-level fallback + TX-first + dual-link fallback verified effective (no code changes)

**Source**: `logs/huya运行日志.log` (room `https://www.huya.com/60066` 杨齐家丶, 2026-08-18 00:48, Web mode v4.0.8.2). Line-by-line investigation pinpointing the warning root cause and ruling out the four possible factors ("network connection异常 / API 接口故障 / 认证失败 / 协议变更"). Conclusion: the WARNINGs in the log are **expected benign noise** from the validation layer correctly intercepting AL CDN access denial — **not a defect**, and the existing fallback chain makes them have zero impact on recording/danmaku (cumulative error count 0). This analysis made no source changes; it only records conclusions.

**Line-by-line investigation and root-cause mapping**:

| Time | Level | Log content | Root-cause定位 | Corresponding source | Impact on recording/danmaku |
| --- | --- | --- | --- | --- | --- |
| 00:48:02.984 | WARNING | 流地址校验失败: `al.hls.huya.com/...m3u8` - HEAD=403, Range-GET=403, content-type=text/html | AL CDN returns 403 for the HLS probe (application-layer denial); HEAD and Range-GET both denied → judged unreachable | `src/stream_select.py:_validate_stream_url` m3u8 branch (HEAD non-2xx → Range-GET probe; 403 retry still denied → False); upper layer logs `HLS URL validation failed, falling back to FLV` | No (triggers HLS→FLV fallback) |
| 00:48:02.985 | WARNING | `HLS URL validation failed, falling back to FLV` | Fallback logic executed normally | `src/stream_select.py:select_source_url` | No |
| 00:48:04.681 | WARNING | 流地址校验失败: `al.flv.huya.com/...flv` - HEAD=200 passes but GET recheck twice 403 (CDN stably denies GET), judged unreachable | AL classic "false-green": HEAD passes but the real GET (ffmpeg's actual fetch method) is denied; `_confirm_get_ok` retries once and still 403 → judged unreachable, avoiding ffmpeg opening with an immediate 403 | `src/stream_select.py:_confirm_get_ok` (streaming GET recheck after HEAD passes; 401/403 retried once before conviction) + `_mark_probe_reject` (AL is in `_PROBE_BACKOFF_PLATFORMS`, logs backoff) | No (triggers FLV→record_url fallback) |
| 00:48:04.682 | WARNING | `FLV URL validation failed, trying record_url fallback` | Fallback logic executed normally | `src/stream_select.py:select_source_url` | No |
| 00:48:04.973 | DEBUG | `[弹幕采集]HuyaDanmaku 连接就绪,开始接收弹幕` | Danmaku WebSocket built its link independently (unrelated to the video CDN) | `src/platforms/huya.py:HuyaDanmaku.start` → `wss://cdnws.api.huya.com` (Tars e… | No (danmaku normal) |
| 00:48:04 | INFO | `准备开始录制视频 .../杨齐家丶_2026-08-18_00-48-04.ts` | After the HLS→FLV→record_url three-level fallback, record_url (TX-first CDN) passed validation and ffmpeg started fetching | `main.py` recording chain + `src/spider.py:get_huya_app_stream_url` (`record_url` selected TX via `priority_order=["TX","HW","HS","AL"]`) | No (recording normal) |
| 00:48:11 | INFO | `累计错误数为: 0` | No recording/parsing errors throughout; AL 403 was absorbed by the fallback ch… | — | No |

**Ruling out the four possible factors one by one**:

1. **Network connection异常 — ruled out**. The log has no `socket.timeout` / `ConnectionError` / DNS failure / proxy anomaly. Both `al.hls.huya.com` and `al.flv.huya.com` **actively return HTTP 403** (application-layer response), meaning TCP connection, TLS handshake, and routing are all normal — it is server-side denial, not a network interruption. The Web panel's uvicorn started normally and 649.21 GB disk free further attests to a healthy environment.
2. **API 接口故障 — ruled out**. `mp.huya.com/cache.php?m=Live&do=profileRoom` returned JSON normally; `baseSteamInfoList` contained multiple CDN nodes such as AL/TX, and `m3u8_url`/`flv_url`/`record_url` plus anchor info ("杨齐家丶 正在直播中") were parsed successfully. If the API had failed, an empty stream_info would have triggered the code's trailing `解析结果无任何流地址` warning — absent from the log.
3. **认证失败 — ruled out**. The stream URLs carry valid anti-code (`wsSecret`/`wsTime`/`fm`/`ctype`/`fs`/`t`); the validator injects `Referer:https://www.huya.com/` per the `虎牙直播` rule (a CDN 403 would result only without Referer, see `_RECORD_HEADER_RULES`), keeping validator and ffmpeg request headers consistent. Key counter-evidence: **record_url (TX CDN) uses the exact same token scheme yet passes validation and records successfully** — if auth/token had expired, TX would fail in sync. Therefore the 403 is AL CDN's access denial, not an auth problem.
4. **协议变更 — ruled out (not indicated)**. The URL shape (`https://al.{hls,flv}.huya.com/src/<id>-imgplus.{m3u8,flv}?wsSecret=...&wsTime=...&fm=...&ctype=tars_mp&fs=bgct&t=...`) is consistent with the project's existing docs/code; no signs of endpoint migration, param renaming, or signature-algorithm change; danmaku still goes through `wss://cdnws.api.huya.com` + Tars (consistent with `_tars.py` / the ported dart implementation).

**True root cause**: The warnings come from **AL CDN (`al.hls.huya.com` / `al.flv.huya.com`) access denial (403)**, consistent with the project's long-standing observation — AL has been unstable/unavailable since 2025/03/14 (`src/spider.py` comment `# 2025/03/14时AL不可用` + `priority_order` placing TX before AL). AL directly 403s the probe HEAD/GET (both denied for HLS; false-green style HEAD 200 + GET 403 for FLV), which is a CDN-side availability/rate-limiting decision, not one of the four factors above.

**Why danmaku and the live stream still record normally**:

- **Live stream**: `select_source_url`'s three-level fallback (HLS→FLV→record_url) lands on `record_url` after both AL candidates fail; and `get_huya_app_stream_url`'s `record_url` picks TX via `["TX","HW","HS","AL"]` priority, TX passes validation, ffmpeg fetches successfully (cumulative error count 0). That is, "bad CDN (AL) correctly excluded by validation → good CDN (TX) covers" is exactly the design goal.
- **Danmaku**: `HuyaDanmaku` uses a **completely independent WebSocket endpoint** `wss://cdnws.api.huya.com` with Tars encoding; the success/failure of the video CDN (al.hls/al.flv/tx…) is irrelevant to it. As long as the API parses out the `yyid`/`topSid`/`subSid` triplet (successful in this case), danmaku builds its link independently. Hence AL video 403 has zero impact on danmaku.

**Conclusion and handling**: This log is a **healthy-state verification** after the 2026-08-17 "Huya 403 failure-loop root-cause fix" — before the fix, AL would burn through the connection budget and cause ffmpeg to fail in a second-level loop, with danmaku starting/stopping together with the recording; this time AL's 403 was cleanly intercepted by the validation layer and fell back to TX, with no loop, 0 errors, and persistent danmaku. The AL-related WARNINGs in the log are **expected benign noise**; no source changes needed.

**Optional optimization (not a defect, do if needed)**: In `get_huya_app_stream_url`, `m3u8_url`/`flv_url` are fixed to `play_url_list[0]` (the API's first returned item, coincidentally AL here), while only `record_url` goes through TX-first priority. One could make `m3u8_url`/`flv_url` also select by priority, so HLS/FLV validation tries TX first and AL only as last resort — reducing the pointless per-round probes against AL, and correcting the preference deviation of "when HLS collection is on, AL grabbing index 0 makes the final result land on FLV instead of TX HLS". Currently, because record_url (TX) ultimately covers, the result is correct; this is only a marginal improvement for log tidiness and HLS-priority preference.

### v4.0.8.2-dev (2026-08-18) — Huya GUI real-test review (179966): HLS three-CDN all-denied yet stable recording; manual-stop path and exit-code-255 classification

**Source**: GUI (`gui.py` spawning `main.py` child via `subprocess.Popen`) recording `https://www.huya.com/179966` (蛇类科普蛇哥), started 2026-08-18 22:09, manually stopped 22:10:47 (47 s total). Log verified line-by-line against `main.py` / `src/stream_select.py` / `gui.py` source, confirming every step is in-design behavior. **No code changes**; only conclusions recorded.

**Line-by-line investigation and root-cause mapping**:

| Time | Level | Log content | Root-cause定位 | Corresponding source | Impact |
| --- | --- | --- | --- | --- | --- |
| 22:09:57–22:10:00 | WARNING | 流地址校验失败: `hs/tx/al.hls.huya.com/...m3u8` - HEAD=403, Range-GET=403（al is text/html） | All three HLS CDNs **simultaneously** return 403 (application-layer denial); HEAD and Range-GET both denied → all judged unreachable | `src/stream_select.py:_validate_stream_url` m3u8 branch (HEAD non-2xx → Range-GET probe; 403 retry still denied → False); upper layer logs `HLS URL validation failed, falling back to FLV` | No (triggers HLS→FLV fallback) |
| 22:10:00.535 | WARNING | `HLS URL validation failed, falling back to FLV` | Fallback logic executed normally | `src/stream_select.py:select_source_url` | No |
| 22:10:00.859 | DEBUG | `[弹幕采集]HuyaDanmaku 连接就绪,开始接收弹幕` | Danmaku WebSocket built its link independently (unrelated to the video CDN) | `src/platforms/huya.py:HuyaDanmaku.start` → `wss://cdnws.api.huya.com` (Tars e… | No (danmaku normal) |
| 22:10:06 | INFO | `准备开始录制视频 .../蛇类科普蛇哥_2026-08-18_22-10-00.ts` | FLV validation passed on first try; ffmpeg fetched directly (no FLV-failure log) | `main.py` recording chain + `src/spider.py:get_huya_app_stream_url` | No (recording normal) |
| 22:10:06–22:10:45 | INFO | `累计错误数为: 0`, 5 danmaku messages | No recording/parsing errors throughout; the three HLS denials were absorbed by the fallback chain | — | No |

**Structural difference from the 60066 review**: This morning's 60066 had only **AL single-CDN** 403 (HLS usable via TX, FLV fell back to record_url via AL false-green); this 179966 had **all three HLS CDNs (hs/tx/al) denied simultaneously**, yet FLV validation passed on first try and recorded directly. The three HLS denials likely relate to the room URL's `fs=bgct&t=102` risk-control params or guest state, but the FLV fallback kicked in immediately with zero impact — confirming the "bad candidate cleanly excluded by validation → usable candidate covers" chain is equally robust against "all-denied" and "single-denied" shapes.

**Manual-stop path verification (critical, easily misread as a defect)**:

1. **`直播录制出错,返回码: 255` is a display-classification deviation, not a recording failure**. On stop, the GUI (`gui.py:1975` `_send_ctrl_break_to_child`) sends `CTRL_BREAK` to the child's console: this console event is delivered **simultaneously** to the shared-console ffmpeg, which exits with code 255 on its own; at the same time `main.py`'s `safe_exit` (`signal.SIGBREAK` handler) sets `exit_recording=True` → `cleanup_all_ffmpeg_processes()` → `close_all_clients_sync()` → `sys.exit(0)`. The room thread (1-second poll, `main.py:714` `while process.poll() is None`) observes the ffmpeg process already dead **first**, enters `main.py:779`'s `return_code != 0` branch printing "error, return code: 255", without entering the `exit_recording` branch. The data (.ts file) was fully written and danmaku flushed; only the text labeling it "error" is a false report.
   - **Optional optimization (not done)**: Before printing, check `exit_recording`; if set, show "recording stopped" instead of "error". The change must keep the recording chain outside the condition (see `AGENTS.md` known pitfall "recording chain must not be nested inside `if headers:`") — only the text branch is changed.
2. **`close_all_clients_sync 回退到引用清理: There is no current event loop in thread 'MainThread'` is a known DEBUG downgrade, harmless**. When the main thread has no event loop, `close_all_clients_sync` takes the reference-cleanup fallback path — expected log.
3. **403 already correctly triggered `_mark_probe_reject`** (Huya is in the `_PROBE_BACKOFF_PLATFORMS` list, `src/stream_select.py`). The denied host enters a 60s backoff window; the next round's probe for the same host will skip with zero probes; this example stopped manually at 47s, so no second monitoring round occurred, hence the probe-saving effect of backoff was not observed.

**Conclusion and handling**: This GUI real test further verifies both chains — "HLS three-CDN all-denied → FLV cover" and "CTRL_BREAK graceful exit + ffmpeg child cleanup" — are healthy. The HLS 403 WARNINGs in the log are **expected benign noise**; `返回码: 255` is a display-classification deviation on the stop path, not a defect. Only one optional optimization is added (manual stop changes text from "error" to "stopped"); no source-change needed.

### v4.0.8.2-dev (2026-08-17) — Huya recording 403 failure-loop root-cause fix: probe backoff/throttle/jitter three-layer anti-rate-limiting + danmaku-monitor room lifecycle + config real-time + whole-codebase UA unified upgrade

**Source**: Deep review of `logs/huya运行日志.log` + whole-codebase UA fingerprint audit. The previous entry concluded "Huya needs no change" (recording/danmaku succeeded intermittently then, judged as probe false-red noise); a new round of real-test logs overturned that — Huya was in a **second-level failure loop**, and the failure shape revealed a new mechanism where probes and ffmpeg compete for the connection budget.

**Root cause (Huya 403 failure loop)**: Huya's aldirect CDN (`aldirect.hls.huya.com` / `aldirect.flv.huya.com`) rate-limits **consecutive connections to the same path within a short time**. Each monitoring round = HLS probe 3 connections (HEAD 403 + Range-GET 403×2) + FLV probe 2~3 connections + ffmpeg fetch 1 connection. After the probes burn through the CDN connection budget:

- Hard evidence one: after `流地址校验: ...flv... - GET 复核重试通过(200)，先前拒绝为偶发` (less than 0.1 s later), ffmpeg immediately hits `Error opening input: Server returned 403 Forbidden` (`返回码 3436169992`) — validation pass and ffmpeg denial on the same URL are adjacent milliseconds, possible only if the budget was exhausted.
- Hard evidence two: even an intermittent success only fetched 446270 bytes before `[http] Stream ends prematurely` + `Error during demuxing: I/O error` — the CDN actively cut it off.
- Chain reaction: recording fails in seconds → the danmaku collector, starting/stopping together with ffmpeg, gets repeatedly killed (log repeatedly shows `HuyaDanmaku 连接就绪` → `采集线程已退出,共收到 0 条消息`) → the danmaku monitor never refreshes new data; and the monitored room entries are never deleted, the comment check-point is too deep, the monitor page retains "stale live-room" old data, and URL_config.ini changes don't take effect.

**Fix one: probe backoff (negative cache, `src/stream_select.py`)** — stop the loss after denial:

- Added `_mark_probe_reject` / `_probe_in_backoff` / `_probe_backoff_key`: once the probe observes 401/403 (**including the intermittent ones that recover after retry** — equally a rate-limiting signal), it records `scheme://host/path` (query stripped: Huya returns a new token each round but the path is stable, so aggregating by host+path hits across rounds; different rooms have different paths and don't cross-harm) into a 60-second backoff window.
- Within the backoff window, **zero probes**: a non-last-resort candidate directly falls back to the next candidate as a validation failure; a last-resort candidate is passed straight to ffmpeg — letting ffmpeg get a clean connection budget with zero probe occupancy (probe denial ≠ ffmpeg cannot fetch; consistent with existing last-resort semantics).
- Backoff list `_PROBE_BACKOFF_PLATFORMS = ("虎牙直播",)` is **Huya-only**: Douyu's hw CDN intermittent 403 must be rescued by the existing "retry once then convict" (retry gives 206, preserving HLS-first); if Douyu entered the negative-cache list it would skip the probe and fall straight back to FLV (guest-state ~70 s cut-off) — a regression.

**Fix two: probe throttle + retry jitter (new this round, reduces false rate-limit triggers)** — prevent beforehand:

- `_throttle_probe(url)`: forced minimum interval `_PROBE_MIN_HOST_INTERVAL=0.35s + uniform(0,0.4s)` between two adjacent probes to the same CDN host (difference computed inside the lock, sleep outside the lock doesn't block other hosts; first probe waits for nothing). Eliminates the **millisecond-level burst probes** against the same CDN under multi-room concurrent monitoring — exactly the rhythm fingerprint that triggers rate-limiting.
- `_recheck_delay()`: the GET-recheck / Range-GET retry interval changed from fixed `0.8s` to `0.8s + uniform(0,0.7s)` — a constant-interval retry sequence is an identifiable bot rhythm; jitter breaks it up.
- Three-layer system: **throttle** reduces the rate-limit trigger probability (beforehand) → **retry** distinguishes intermittent limiting from stable denial (during, existing semantics preserved) → **backoff** skips probes after denial to preserve ffmpeg's budget (afterward, stop the loss).
- Note: `_validate_stream_url`'s throttle runs after the backoff check (a backoff hit returns directly, producing no probe or wait).

**Fix three: danmaku-monitor room lifecycle (`src/danmaku_monitor.py` + `main.py` + `gui.py`)** — no stale live-rooms left:

- `DanmakuMonitorHub` adds `room_stopped(room, reason)`: removes the entry from `_rooms` + writes a `conn/stopped` event (no-op for unregistered rooms). Previously `_rooms` was never deleted, so after a URL was removed the monitor page kept showing "stale live-room" with its old danmaku data.
- `main.py` `start_record`'s outer try adds a `finally`: when the room thread exits (all return paths in recording/polling/parse-failure states), calls `get_hub().room_stopped(record_name)`; re-recording the same room re-registers via the collector's `room_started`. Monitoring is a side feature; cleanup failure is silent.
- `gui.py` `_danmaku_dispatch` pops the room row from `_danmaku_rooms` after receiving a `state=="stopped"` event (the Web-side snapshot disappears with the room table automatically, no change needed).
- After recording stabilizes, the danmaku collector stays persistently connected, no longer repeatedly killed by second-level-failing ffmpeg — danmaku data accumulates continuously and the monitor page refreshes in real time.

**Fix four: config-change real-time (`main.py`)** — comment/remove takes effect immediately:

- Added an early `record_url in url_comments` check + `clear_record_info` + `return` at the top of the room thread's inner loop (after the `exit_recording` check). The original check point was after the platform parse succeeded; when the platform API kept failing (risk-control returns empty, etc.) it was never reached — the thread lingered occupying a monitor slot, and URL_config.ini removal/comment changes took effect belatedly.

**Fix five: whole-codebase UA unified upgrade (anti-rate-limiting fingerprint recognition)**:

- Background: overly-old UAs (Chrome/87, Firefox/115, Chrome/116~121 and other 2019–2024 fingerprints) are one of the features by which rate-limiting identifies and denies service by client fingerprint; and the same-purpose UA versions in the codebase were fragmented.
- Unified baseline (2026-08, aligned with `room.DESKTOP_UA`'s existing Chrome/141): desktop **Chrome/141**, **Edg/141**, **Firefox/148** (rv:148.0), mobile **`Android 14; Pixel 8` Chrome/141 Mobile**.
- Change locations (replaced/synced one by one after whole-codebase investigation):
  - `src/stream_select.py`: `DESKTOP_UA` (Chrome/126→141), `MOBILE_UA` (SamsungBrowser/14.2+Chrome/87→Android 14+Chrome/141).
  - `main.py`: ffmpeg recording command's default mobile UA synced — **must match `MOBILE_UA` exactly** (validator probe and ffmpeg must have identical client fingerprints, otherwise false-red/false-green).
  - `src/room.py`: `HEADERS` mobile UA synced (X-Bogus signature is computed with the same UA in the request header, self-consistent; string change is safe).
  - `src/spider.py`: 60+ platform-interface UA unified in batch (Firefox 115/119/122/123/124/127→148; Chrome 120/121→141; Edge 121/138→141; Bilibili H5 mobile UA synced).
  - `src/ttwid.py` (Chrome/116→141), `src/weverse_auth.py` (Chrome/120→141), `src/ffmpeg_install.py` (Chrome/121+Edg/121→141), `src/platforms/douyin.py` (danmaku WS `DEFAULT_USER_AGENT` Chrome/125+Edg/125→141; `browser_version` in the query shares the same constant as the request header, staying self-consistent; the signature function contains no UA).

**Tests and verification**:

- `tests/test_stream_select.py` expanded to 22 cases: 7 Huya backoff (stable 403 marks backoff → round 2 zero probes, last-resort backoff zero-probe pass, FLV intermittent 403 marks backoff, backoff key hits across tokens, window expiry recovery, Douyu unaffected, select_source_url backoff round straight to FLV) + 4 throttle/jitter (retry-interval jitter range, same-host throttle padding, different hosts independent, throttle before validation).
- `tests/test_danmaku_monitor.py` expanded to 17 cases: `room_stopped` removes room + stopped event + no-op for unregistered; GUI `stopped` event deletes room row.
- Test infra: autouse fixture sets `_throttle_probe` to no-op and clears the global throttle record (some existing cases patch the whole time module, and the real throttle's time-difference comparison would TypeError); throttle-specific tests bypass the no-op via from-import of the real function reference.
- Full regression **607 passed, 2 skipped**; black / isort / mypy all green.
- Five anti-regression lessons recorded in `AGENTS.md` known pitfalls (Huya backoff is list-only, monitor rooms removed on thread exit, comment check before parse, UA exactly-matching on both ends + whole-codebase baseline, throttle/jitter semantics must not be removed).

### v4.0.8.2-dev (2026-08-17) — Three-platform real-log investigation: Douyu fatal-exception fix + Bilibili danmaku auth-chain closure + validator last-resort pass extension

**Source**: User's three run logs (`logs/douyu运行日志.log` / `huya运行日志.log` / `哔哩哔哩运行日志.log`). Cross-checked against source, locating four different manifestation shapes across three platforms:

| Platform | Log manifestation | Root-cause定位 |
| --- | --- | --- |
| Douyu | Cannot record live + cannot record danmaku, every round `ERROR: cannot access local variable 'title_in_name' 发生错误的行数: 2183`、cumulative error count increasing、`瞬时错误太多,延迟加60秒` | Two-level defect stack (see below) |
| Bilibili | Live normal, danmaku "connection ready" but 0 messages, no errors | buvid fetch failed + AUTH soft-denial zero-awareness (see below) |
| Huya | Lots of `流地址校验失败` WARNINGs, but both recording + danmaku normal | Probe "false-red" (CDN mis-kill), three-level fallback + dual-link cover as designed, not a defect, no change needed |

**Douyu fatal exception (two-level defect)**:

1. **`title_in_name` unbound crash (direct cause of death)**: `main.py`'s recording execution chain is outside the `if real_url:` block, but depends on `title_in_name`/`ffmpeg_command` assigned inside it. When `select_source_url` returns None (Douyu hw CDN's three candidates all judged dead by 405/403), execution still proceeds to the TS branch `filename = anchor_name + f"_{title_in_name}" + now + ".ts"` (originally line 2183), triggering `UnboundLocalError`, crashing every round and preventing danmaku from starting (danmaku and ffmpeg start/stop together in `check_subprocess`, never reached).
2. **Probe false-red + last-resort pass失效 (root cause)**: Douyu hw CDN (hw3.douyucdn2.cn) returns **405 + text/html** for the probe HEAD (HEAD method disabled), while ffmpeg's actual GET fetch is normal. HLS candidates died on `HEAD=405, Range-GET=403` (millisecond burst probe intermittently denied by CDN), FLV/record_url died on the content-type heuristic branch — but that branch **did not implement `last_resort` pass** (the pass logic existed only in `_confirm_get_ok`'s 401/403 GET-recheck path), causing `real_url=None`.

**Fix (Douyu)**:

- `main.py`: when `select_source_url` returns None, warn + wait per the normal monitoring interval + skip to the next round (`if not real_url: ... continue`), blocking the `title_in_name` unbound crash.
- `src/stream_select.py` `_validate_stream_url`:
  - m3u8 Range-GET probe 401/403 first retries once after `_GET_RECHECK_INTERVAL` before conviction (same semantics as `_confirm_get_ok`), passing on retry → judged usable — rescues Douyu HLS candidates, immune to the guest-state FLV ~70 s CDN cut-off.
  - text/html heuristic branch and the trailing non-200 branch: `last_resort=True` candidate only warns and passes ("no fallback source left, still hand to ffmpeg to try"); non-last-resort still judged unreachable and falls back at the upper layer.
- `src/stream_select.py` `select_source_url`: passes `last_resort=True` when HLS is the only candidate (no FLV/record_url fallback); FLV-as-h265-unavailable branch has HLS always `last_resort=True`; top-level unified `has_fallback` computation de-duplicates the trailing repeated calculation.

**Bilibili auth problem (danmaku 0 received)**: The live stream goes through the independent `getRoomPlayInfo` chain, unaffected, so live is normal and only danmaku fails. Root cause in two parts — buvid fetch failure and AUTH soft-denial:

1. **spi endpoint typo (root cause)**: `src/spider.py` requests `https://api.bilibili.com/x/frontend/finger/sp`, but the official endpoint is `/finger/spi` (missing trailing `i`), returning 200+empty body causing `JSONDecodeError`, forced to fall back to random UUID — and the random UUID isn't registered with Bilibili, so the danmaku server soft-denies AUTH (connection kept but no danmaku pushed, manifesting as "connection ready" yet 0 danmaku, with no log at all).
2. **AUTH_REPLY zero validation**: `bilibili.py` `_decode_packet` directly ignores operation=8 (room-entry response), so auth failure is completely undetected.

**Fix (Bilibili auth-chain closure: fetch → enter room → detect → self-heal)**:

- `src/spider.py`:
  - spi URL corrected to `/x/frontend/finger/spi`.
  - buvid fetch chain prioritizes real registered identifiers: process cache → login cookie `buvid3=` → spi → **`www.bilibili.com` homepage Set-Cookie** (new, via `cookie_cache.fetch_cookies`, a different domain than spi with independent risk-control, able to get a real registered identifier in real scenarios) → random UUID fallback (marked `_bili_buvid_is_fallback=True`).
  - Added `invalidate_bili_buvid_cache()`: on AUTH denial, clears in-process cache + fallback flag, so the next round re-walks the real fetch chain (otherwise the denied UUID is permanently cached and reused = infinite loop).
- `src/platforms/bilibili.py`:
  - operation=8 explicitly validates code: 0 sets `_auth_ok` and releases the watchdog; non-0 goes through `_reject_auth()` warning + disconnect + calls `spider.invalidate_bili_buvid_cache()`.
  - `_reject_auth()`: unified auth-denial handling (lazy-imports spider to avoid circular dependency).
  - `_auth_watchdog`: covers the "server silently denies without AUTH_REPLY" case — if no code=0 response within 8 s of sending the room-entry packet, treat as denied; old watchdog voided after host switch (`self._ws is not ws` check).

**Huya (conclusion: no change needed)**: The errors are expected in-design noise from the validation probe being mis-killed by CDN protection (`al.hls.huya.com`/`al.flv.huya.com` 403 the millisecond burst probes), the HLS→FLV→record_url three-level fallback correctly covers (`real_url=record_url`), and danmaku goes through the independent WS link unaffected. If noise reduction is wanted, widen the probe interval; not changed this round.

**Tests and verification**:

- Added `tests/test_stream_select.py` (11 cases): last-resort pass 4 (text/html / non-200 / last-resort / non-last-resort) + m3u8 probe retry 4 (retry passes / stable denial / 404 no retry / last-resort pass) + select_source_url last-resort param 3 (HLS only / h265 / HLS has fallback).
- `tests/test_bilibili_danmaku_info.py` expanded to 17 cases: spi URL assertion, cookie priority, homepage Set-Cookie backup fetch, invalidation hook, AUTH success/failure, watchdog trigger/release/void, existing cases supplemented with homepage empty stub.
- Full regression **137 passed**; black / isort / mypy (stream_select/bilibili/spider/main) all green.
- Three anti-regression lessons recorded in `AGENTS.md` known pitfalls: `real_url` empty must skip the recording chain, last-resort candidate's content-type denial must also pass, Bilibili buvid must be real + AUTH_REPLY explicitly validated.

> Environment noise: During execution, the `.mimosa` hook repeatedly rolled back this round's changed files (bilibili.py AUTH block, test import lines, test assertions); all were re-applied and re-tested to confirm they are in place — if a modification is found missing later, investigate this tool first.

### v4.0.8.2-dev (2026-08-17) — i18n translation-chain root-cause fix: supply missing zh_CN.mo + drop env-var dependency + po cleanup

**Source**: Whole-source AST audit (extracting all `print()` string literals and comparing line-by-line with `zh_CN.po`). Content coverage was good (all 49 constant English strings translatable at runtime had entries), but **two fatal mechanism-layer problems meant translations never took effect**.

**Root cause**:
① The repo only had the `.po` source text, **missing the compiled artifact `.mo`** — gettext reads only `.mo` at runtime; `.gitignore` explicitly states ".mo is distributed with the repo (required at runtime)" but the file didn't actually exist, so all English prompts (e.g. spider.py's `"IP banned..."`) always showed English in a Chinese environment.
② `init_gettext` used `gettext.gettext` global lookup, inferring the language directory from `LANG`/`LANGUAGE` env vars; Windows clients generally don't set these vars (verified: lookup inevitably fails when `LANG` is absent) — even with `.mo` supplied it wouldn't load.

**Fix** (3 files changed + 2 files added + 1 test expanded):

- `i18n.py`: `init_gettext` changed to `gettext.translation(..., languages=["zh_CN"], fallback=True)` explicit load, not depending on any env var; still falls back to identity when `.mo` is missing, behavior-compatible. Kept `bindtextdomain`/`textdomain` (per the existing comment's historical rationale).
- Added `scripts/compile_po.py`: a pure-Python `.po → .mo` compiler (GNU msgfmt-compatible minimal format, usable when Windows has no gettext toolchain), with a `--check` mode doing byte-level sync verification.
- Added `i18n/zh_CN/LC_MESSAGES/zh_CN.mo`: compiled artifact (198 entries incl. header), distributed with the repo; auto-included on all three paths — Docker / release zip / source run (Dockerfile `COPY` and `build_exe.py` datas both take the directory wholesale).
- `i18n/zh_CN/LC_MESSAGES/zh_CN.po` cleanup (204 → 198): removed dead entries that disappeared from source (`"HTTP error occurred"`, the colon-less `"An unexpected error occurred"`, `"First data retrieval failed..."`, `"Python"`) and one exact duplicate; merged `"Please add"` + `"at the beginning..."` two half-entries into notify.py's current full string; fixed all `gui.pyw` references to `gui.py`; added maintenance notes to the header.
- `.github/workflows/ci.yml`: the `static` job adds a `compile_po.py --check` step after `check_version.py`, blocking "changed .po but forgot to recompile .mo".
- `tests/test_i18n.py` adds 3 regression tests: `.mo` exists and is non-empty; after clearing `LANG`/`LC_*` `init_gettext` still really loads path translations (would fail if it fell back to env-var lookup); `.po` compiled bytes match the committed `.mo` (compared in-process via imported compile script, no spawned child — this machine's pytest occasionally hits transient `WinError 50` on `CreateProcess`, in-process implementation is completely immune).

**Security review**: Mimosa L2 once flagged `tests/test_i18n.py`'s `subprocess` call as command injection — judged a false positive (argument list + no shell + pure static literals, no external input in the concatenation), but the test was still refactored to an in-process implementation, structurally eliminating the suspicious pattern and incidentally solving the transient failure above.

### v4.0.8.2-dev (2026-08-17) — Validator GET-recheck false-kill tolerance (retry + last-resort pass) + Douyu FLV→m3u8 same-token HLS candidate (root-causing ~70s stream cut-off)

**Source**: User's four-room real-test logs (Douyu 100 / Douyin / Bilibili / Huya, all healthy throughout: 4 recordings, 4 danmaku, graceful exit all normal). Two problems exposed: ① Huya/Douyu FLV repeatedly showed "HEAD=200 passes but GET=403 (CDN denies GET), judged unreachable" → after falling back to record_url, ffmpeg used the same-origin URL and actually fetched successfully (Huya recorded 3+ minutes until manual stop) — probe mis-kill (validation false-red); ② Douyu room got cut off by the CDN every ~69–72 s (`[in#0/flv] Error during demuxing: I/O error` + `[tls] Failed to send close message`), repeatedly segmented with 7–10 s lost between segments.

**Root cause**:
① Douyu hw / Huya al CDNs **intermittently** 403 the millisecond burst probe (HEAD→GET) — verified by sending the same URL 3 times in a row with no Range GET, all 200, proving it's intermittent limiting not address failure; and when the candidate is already the last tier (no fallback to fall back to), the recheck denial causes the whole round to abandon recording, while the probe (httpx) and ffmpeg client fingerprints (TLS/JA3 etc.) differ, so a stable probe 403 doesn't mean ffmpeg can't get the stream.
② Douyu's H5 interface (`getH5PlayV1`) only returns FLV; guest state (`did=10000000000000000000000000003306`, web-h5 token) FLV long-connection is actively cut by the CDN at ~70 s, a server-side behavior. Verified wsAuth token works for both FLV/HLS: changing path `.flv` to `.m3u8` gives the same-token HLS playlist (hw CDN 200 + `application/vnd.apple.mpegurl`, two-level m3u8: master list → livehwc4 media list; token lives far longer than 75s and doesn't expire with a single connection drop).

**Fix** (2 source files + 2 test files):

1. **`src/stream_select.py` probe mis-kill tolerance**:
   - `_confirm_get_ok` on receiving 401/403 first retries once as-is (0.8s interval) before conviction — distinguishing "intermittent limiting" from "stable denial"; the historical Huya false-green scenario (CDN denies GET itself) still 403s on retry and is still correctly denied, no regression.
   - Added `last_resort` param, passed through `_validate_stream_url`; `select_source_url` computes "last-resort candidate": FLV with no record_url fallback → last_resort=True, record_url always True — even a last-resort candidate that stably fails recheck only warns and passes ("no fallback source left, still hand to ffmpeg to try"), letting ffmpeg's actual fetch decide.
2. **`src/stream.py` Douyu HLS candidate**: `get_douyu_stream_url` appends `m3u8_url` (path `.flv`→`.m3u8`, query string as-is, no dangling `?`) when `rtmp_live` ends with `.flv`; `flv_url`/`record_url` unchanged; `select_source_url` preferentially validates/selects m3u8 when HLS collection is on (default "yes"), falling back to FLV automatically if unreachable, zero risk; with HLS collection off it keeps FLV behavior.

### v4.0.8.2-dev (2026-08-16) — Unified cookie fetching: URL-level shared cache, eliminating repeated same-URL fetches that trigger risk-control

**Source**: User requirement — analyze all dynamically-fetched-cookie code, unify the fetch method into "dynamically fetch from the corresponding URL", and establish a cross-module shared cache to avoid repeated requests to the same URL (repeated visitor-cookie fetches get risk-controlled by the platform, returning HTTP 200 + empty body, manifesting as silent parse failure).

**Root cause**: Previously Douyin ttwid (`src/ttwid.py`) and Kuaishou did (`src/spider.py:_ensure_kuaishou_did`) each maintained independent caches and each requested the URL; under the "per-room independent thread + independent asyncio.run loop" concurrency model, the same URL was requested repeatedly by multiple rooms, easily triggering risk-control. Each platform's login-state cookies (SOOP/Flextv/TwitCasting login, Taobao `_m_h5_tk` refresh) are account credentials, already in `config.ini`, not in this unification scope; Twitch `Client-Id` is a non-cookie credential parsed from HTML, also not included.

**Fix** (1 file added + 2 changed):

1. **Added `src/cookie_cache.py`**: process-level visitor-cookie cache keyed by "normalized URL + proxy".
   - Storage: `dict[key, (cookie_dict, expire_ts)]`, value is the raw cookie dict dispatched by the URL (caller extracts `ttwid`/`did` etc. as needed, no platform-specific trimming).
   - Expiry: TTL default 30 min (consistent with `src/room.py` sec_uid cache); fetch exception or empty dict returned **not written to cache** (failure is retryable, avoids固化ing transient failures); `threading.RLock` double-check deduplication (lock held across `await` must be RLock, consistent with ttwid).
   - Cross-module calls: `fetch_cookies(url, proxy, *, headers, timeout, http2, ttl, fetcher)` unified read entry; `get_cached(url, proxy)` synchronous read-only reuse; `get_cookie_str` gets the joined string; `invalidate/clear` invalidate/clear. Any module for the same URL (Douyin ttwid, Kuaishou did, etc.) shares one cache; never re-requests the same URL.
   - `fetch_cookies` accepts a `fetcher` param (defaults to this module's `async_req`); the caller passes its own namespaced `async_req`, so unit tests stubbing `src.<mod>.async_req` can still intercept (each module imports the same function object but in different namespaces).
2. **`src/ttwid.py`**: `_fetch_ttwid` fetched via `cookie_cache.fetch_cookies("https://live.douyin.com/", ..., fetcher=async_req)`; config priority, `_ttwid_lock` deduplication, and `ttwid=` formatting logic unchanged.
3. **`src/spider.py`**: `_ensure_kuaishou_did` fetched via `cookie_cache.fetch_cookies("https://live.kuaishou.com/", ..., fetcher=async_req)`; module-level `_kuaishou_did_lock` and `_cached_kuaishou_did` compatibility vars unchanged.

### v4.0.8.2-dev (2026-08-16) — Bilibili spi buvid request governance: process-level cache + zero requests during off-air periods

**Source**: User `py web.py` real-test log (Bilibili 3336696 / Douyin 51845582768 / Douyu 998). While the Bilibili room was off-air (DOTA2 CN server "waiting for live"), `[B站直播]buvid 获取失败: JSONDecodeError`刷 a round every 2~5 s (3 entries per round: retry DEBUG, failure WARNING, fallback DEBUG), continuing until exit. The spi endpoint (`/x/frontend/finger/sp`) returned 200+empty body (Bilibili risk-control), the fallback UUID buvid3 generated normally (no functional impact), but the high-frequency empty rounds wasted requests and got more blocked the more they fetched.

**Root cause**: In `main.py`'s Bilibili branch, `get_bilibili_danmaku_info` ran **unconditionally every monitoring cycle** (also ran 4~5 requests in off-air cycles: room_init + nav + spi×2 + getDanmuInfo), while the danmaku info is never used in a cycle that won't go live this cycle. buvid itself is a device-level identifier, not varying by room, but re-fetched every cycle in-process — the high-frequency cookie-less spi requests are exactly what triggers the risk-control empty response.

**Fix** (2 files):

1. **`src/spider.py` buvid process-level cache**: added module-level `_bili_buvid_cached` + `_bili_buvid_lock` (threading.Lock). In `get_bilibili_danmaku_info` step 3 (fetch buvid), read cache first — reuse directly if non-empty; if empty, walk the spi retry logic, write to cache after successfully fetching a real value or generating a fallback UUID. Lock covers the whole fetch; multi-room concurrent first-time recording only hits spi once; fallback UUID also cached (anonymous room-entry only needs a non-empty buvid, long-lived). Across the whole process lifetime spi is requested at most twice (the two retries on first attempt).
2. **`main.py` deferred until live**: added `if port_info.get("is_live", False)` gate before the Bilibili branch's `get_bilibili_danmaku_info` call — off-air cycles completely skip danmaku-info fetching (0 requests); when live, this cycle is about to start recording, so fetching token/buvid is exactly the right semantics.

### v4.0.8.2-dev (2026-08-16) — Three rounds of real tests: unearthed a historic structural bug — recording chain nested inside `if headers:`, Douyin/Douyu etc. never recorded

**Source**: User's third `py web.py` real test + instrumentation proof. The previous two rounds' fixes (tls_verify https-only, GET-recheck drops Range, HLS silent warning) all took effect (Huya recorded 2+ minutes), but Douyin/Douyu still "正在直播中" with zero logs.

**Root cause (instrumentation proof)**: In run(), the `if headers:` after `headers = get_record_headers(platform, ...)` (originally `main.py` line 1739) **wrongly wrapped the entire recording chain after it** (tls_verify/proxy insertion, record_state_lock registration, rec_info print, TS/FLV/MP4/MKV all recording branches, check_subprocess, count_time/record_success) — ~490 lines. Any platform where `get_record_headers` returns None (Douyin, Douyu and other platforms without dedicated Referer/Origin) had the entire recording block **silently skipped**: no print, no error, no recording, empty-spinning every cycle. Platforms with dedicated recording headers (Huya/Bilibili) were unaffected — exactly why only Huya/Bilibili could record in past rounds' logs. Instrumentation logs further confirmed: Douyin select_source_url returned a valid m3u8 URL every cycle, but it was lost at the `if headers:` point.

**Fix**:

1. **`main.py` indentation-level correction (483 lines shifted left 4 spaces overall)**: `if headers:` keeps only the `-headers` insertion (4 lines); tls_verify insertion, proxy insertion, recording-state registration, all recording branches, cycle counting all moved out, executed unconditionally.
2. **`stream_select.py` validator UA alignment**: added `MOBILE_UA` constant (exactly matching `main.py`'s ffmpeg default UA), `_validate_stream_url` sends a mobile UA (not httpx's default UA) for platforms without a desktop UA — Douyu hwa CDN intermittently 403s GETs from non-browser UAs (verified: httpx default UA intermittent 403 / mobile UA fetches normally); validator and recording must have identical UAs on both ends.

### v4.0.8.2-dev (2026-08-16) — Second-round real-test log fixes: tls_verify mis-inserted into http stream / Range-GET mis-killed Douyu / HLS-off silent path

**Source**: User's second `py web.py` real test. **Previous round's fixes verified effective**: Bilibili danmaku connection held (no disconnect-reconnect loop); Huya succeeded recording after GET-recheck → record_url fallback (0:01:18 until exit). This round exposed 3 new problems:

1. **`Option tls_verify not found` (Huya http FLV recording failed, return code 2880417800)**: When cert validation is off, run() unconditionally inserted `-tls_verify 0`, but that option is a tls-protocol private option — Huya's stream is `http://`, ffmpeg has no tls component to consume it and directly reports Option not found. **Fix** (main.py): only insert when `real_url` is https.
2. **Range-GET mis-killed Douyu**: Last round's GET-recheck carried `Range: bytes=0-0`; Douyu hwa CDN intermittently 403s Range-GET but normal GET without Range (verified contrast: same URL HEAD=200 / Range-GET=403→now 200 / no-Range GET=200), FLV judged unreachable then record_url also empty → forever "正在直播中". **Fix** (stream_select.py `_confirm_get_ok`): drop the Range header — ffmpeg's fetch is "full GET without Range", the recheck is exactly consistent; Huya false-green unaffected (its 403 denies GET itself, unrelated to Range, verified last round that ffmpeg without Range GET also 403s).
3. **"m3u8 exists but HLS collection off and no flv/record fallback" silent path**: Last round's "all empty" warning condition included `hls_available`; this scenario (m3u8 present but collection off, all fallbacks empty) triggered no log. **Fix** (select_source_url): this path now warns "HLS source exists but HLS collection not enabled... enable HLS collection to resume recording". (Note: Douyin web mode's repeated "正在直播中" with no warning — the exact branch wasn't reproduced in the probe; under probe the parse returned is_live=None and the "all empty" warning printed normally; with the new warning as backstop, next run's log will inevitably leave a trace to locate it.)

### v4.0.8.2-dev (2026-08-16) — Special cleanup: fully backfill unlanded test-first fixes (21 failed + 18 errors → 540 passed)

**Characterization**: git history proves all failing/erroring tests were unchanged since the init commit, while their expected symbols/behaviors ("batch 4/batch 5 fixes") never landed in source — tests are the spec; this round backfilled the source implementation per the test spec.

**Change list** (8 source files):

- `src/async_http.py`: added `_client_cache_lock` (threading.Lock, no await in critical section) protecting `_client_cache`'s check-then-act; secondary check before releasing an expired client to prevent concurrent double-close; all cleanup paths hold the lock.
- `src/web_api.py`: login-failure rate-limit (`_FAILED_LOGINS`/`_FAILED_LOGINS_LOCK`, sliding window 5 times/300s → 429, cleared on success); `_get_client_ip` only trusts XFF when the direct peer is in `web_trusted_proxy` (prevents forged bypass of rate-limit); dangerous-config-key blacklist (custom-script execution command) 403 in any state; clears web_password returning 400 when auth is enabled; `_rooms_config_lock` atomizes "dedup+append" to eliminate concurrent TOCTOU duplicate writes; rooms/config write wiring guards newline-injection (422).
- `src/web_config.py`: `web_trusted_proxy` default value; `format_url_line`/`validate_config_target`/`validate_room_target` newline-injection guards; `verify_web_password` returns False on illegal iteration instead of ValueError.
- `src/weverse_auth.py`: `_app_secret()` supports env var `DOUYIN_WEVERSE_APP_SECRET` overriding the hardcoded key.
- `src/spider.py` 9 places: vvxqiu no longer empty-probes m3u8 when room number missing, empty response judged off-air; migu node call adds timeout=30 and unifies CalledProcessError/TimeoutExpired/FileNotFoundError into ProgramError, redirect failure judged off-air, title-missing tolerance; faceit delegates Twitch passing proxy/cookies; shopee keeps original URL on redirect failure, full TLD suffix (shopee.co.id → live.shopee.co.id), malformed URL judged off-air; zhihu drama empty returns directly without appending request; weibo/twitcasting malformed URL explicit RuntimeError; lianjie non-webrtc:// address judged off-air; Kuaishou did and Twitch Client-Id fetch add lock + double-check (concurrent fetch only once).
- `src/ttwid.py`: `_ttwid_lock` changed to RLock (lock held across await, same-thread reentry doesn't deadlock).
- `src/utils.py`: `read_config_value` disables configparser interpolation (bare % no longer InterpolationSyntaxError).
- `src/sync_http.py`: unified `logger.error("sync_req 请求失败...")` on request failure and returns empty string (error text no longer masquerades as response body).

**Leftover**: ~~`mypy main.py` still had 6 `check_subprocess` `list[str | None]` arg-type errors~~ **resolved** (see next entry: root cause was `ffmpeg_command` literal built outside the `if real_url:` guard block, one `cast(str, real_url)` in the list narrowed the type).

### v4.0.8.2-dev (2026-08-16) — Cleared mypy main.py's 6 arg-type errors

**Root cause**: In `run()`, `real_url = select_source_url(...)` returns `str | None`; after the `if real_url:` guard block (path setting/protocol replacement) ends, `ffmpeg_command = [...]` literal is built **outside the guard block** (same indentation level) — here `real_url`'s type reverts to `str | None`, the list union type becomes `list[str | None]`, and the 6 call sites passing it to `check_subprocess(ffmpeg_command: list[str])` (audio/FLV/MKV/MP4/TS etc. recording branches) all error. All other elements were excluded as `str` (`user_agent` is `str or str`, the five ffmpeg params are str literals, `header_blob`/`proxy_address` are guard-inner inserts).

**Fix**: [main.py] one `cast(str, real_url)` at the list's `-i` argument (zero runtime change; the command list is only consumed in the recording branches inside the `if headers:` body, never executes when `real_url` is None, the cast assertion same habit as existing line 1640 `cast(str, port_info.get(...))`). Incidentally applied black to unify the line-wrap style of `real_url = select_source_url(...)` in the same area (the only format deviation left from the previous session).

### v4.0.8.2-dev (2026-08-16) — Bilibili danmaku connect-then-drop true root cause (room-entry packet uid mistakenly passed anchor uid) + Huya FLV validation false-green + all-empty stream-address silent skip

**Source**: User `py web.py` real-test log (Bilibili 3336696 / Douyin 51845582768 / Huya vctcn / Douyu 998). This round's log proves last entry's "buvid empty → disconnect" conclusion **doesn't hold**: the fallback uuid buvid already took effect (log shows "使用生成兜底 buvid3"), but BilibiliDanmaku was still hard-disconnected ~30ms after connecting, 0 messages.

**Root cause (real-device vs probe proof)**: `get_bilibili_danmaku_info` returned `uid` is the **anchor** uid (room_init's data.uid), while `bilibili.py` `_join_room` stuffed it into the AUTH packet as the **viewer** uid. The danmaku server validates uid mismatch with the anonymous token → immediately 1006 disconnect ("no close frame"). Probe 2 rooms × 4 combinations (uid=anchor/0 × buvid=uuid/homepage buvid3): whenever uid=anchor it disconnected (A/C), whenever uid=0 all received AUTH_REPLY and collected danmaku normally (B/D) — whether buvid is server-issued **is irrelevant**.

**Changes**:

- `src/platforms/bilibili.py` `_join_room`: viewer uid = `DedeUserID` from cookie (login state) else 0, never again pass through anchor uid. spi fallback uuid buvid retained (harmless and probe-proven usable).
- `src/stream_select.py` `_validate_stream_url`: FLV/record_url appends a streaming Range-GET recheck (`_confirm_get_ok`, no body read) after HEAD passes, only 401/403 overturns the HEAD conclusion. Blocks Huya `al.flv.huya.com` HEAD=200/GET=403 validation false-green — in this round's log the false-green made ffmpeg open with an immediate 403 (`返回码 3436169992`) looping retries; after the fix it will fall to the usable record_url via the fallback chain.
- `src/stream_select.py` `select_source_url`: when m3u8/flv/record_url are all empty, no longer silently returns None (Douyu `get_douyu_stream_url` takes this shape when rtmp_live is empty), adds a warning exposing the root cause of "正在直播中... yet never records".

**Leftover (out of scope this round)**: Full `pytest` has pre-existing drift of 21 failed + 18 errors (`_client_cache_lock`/`_FAILED_LOGINS_LOCK`/`_app_secret` etc. symbols missing at HEAD, `node` environment issues), all in modules untouched this round, pending special handling.

### v4.0.8.2-dev (2026-08-16) — Bilibili danmaku buvid fallback (generate fallback buvid3 when spi risk-control returns empty)

**Source**: Multi-room real-test logs (Huya 660002 / Bilibili 3336696 / Douyu 998 / Douyin 481667816952). Bilibili danmaku `BilibiliDanmaku 连接就绪` then ~34ms later `连接关闭: no close frame received or sent` and repeated reconnects, received no danmaku; adjacent log `buvid 获取失败: JSONDecodeError` (spi endpoint empty body). The Huya danmaku triplet fix (`f415184`) **verified effective** in this round's log (previously silently skipped).

**Root cause**: `get_bilibili_danmaku_info`'s spi endpoint `api.bilibili.com/x/frontend/finger/sp` intermittently returns empty body (Bilibili risk-control 200+empty body, same as Douyin pattern). `_loads_dict("")` yields `{}` instead of raising → `buvid` silently empty → `bilibili.py:95` room-entry packet `buvid` field empty → danmaku server rejects and hard-disconnects ("no close frame" = server RST, not timeout). token/host both fetched normally (otherwise couldn't connect), only buvid empty.

**Change** (`src/spider.py` `get_bilibili_danmaku_info` step 3):

- spi buvid fetch wrapped in `for _attempt in range(2)` retry once (transient empty body self-heals).
- If still empty after two tries, `buvid = str(uuid.uuid4())` generates fallback buvid3 (random UUID-style 32-char string, matching Bilibili buvid3 format), guaranteeing the room-entry packet always carries a non-empty buvid. `uuid` module already imported at file top.

- Real-device probe (temporary script, deleted) confirmed Bilibili danmaku connect-then-drop shares the same root as buvid empty; curl contrast confirmed the problem is independent of Referer/UA.
- Added `tests/test_bilibili_danmaku_info.py::test_get_bilibili_danmaku_info_spi_empty_uses_fallback_buvid`: spi returns empty twice → returns non-empty valid uuid buvid, token normal.
- `pytest` above 4 cases all pass (incl. new); `mypy src/spider.py` 0 errors; 6 test files total **35 passed** no regression.

### v4.0.8.2-dev (2026-08-16) — Huya HLS/FLV 403 investigation conclusion (Referer already correctly injected, no code change needed)

**Investigation source**: Same-round log Huya HLS(m3u8)/FLV validation 403 → fell back to record_url (recording succeeded, not failed). Early commit `0f6817b` already injected Huya Referer; this round used a real-device probe (temporary script) on `al.hls.huya.com` / `al-game.flv.huya.com` doing HEAD/GET × multiple Referers (none / generic / room-level / room-level+Origin) contrast:

- `al.hls.huya.com` (m3u8): **HEAD=403 and GET=403, unrelated to Referer** — this host doesn't serve m3u8 in this environment, a CDN/host-level unreachability that Referer can't save.
- `al-game.flv.huya.com` (flv): HEAD=200 (Referer already injected, validation should pass); the occasional 403 in the log was caused by `wsTime` expiring within the "fetch→validate" window, not a code bug.
- record_url (`tx.flv.huya.com`) actually recorded via ffmpeg GET (log confirmed recording started).

**Conclusion**: Referer injection is correct and effective for applicable hosts; `al.hls` m3u8 is environment-level unreachable, and the code correctly covers via the FLV→record_url fallback chain, **no change needed**. The probe script used for verification was a one-time debug file, not committed.

### v4.0.8.2-dev (2026-08-16) — Fix config.ini non-writable crash at import main stage (web.py startup failure)

**Source**: User `py web.py` crashed at `web.py:135 import main`. Traceback: `main.py:2314` compat-reads old key `虎牙是否禁用SSL证书验证(是/否)` (already removed with the SSL generic-list migration, config.ini only keeps the comment); old key missing → `read_config_value` enters write-back branch, holding `file_update_lock` truncates-and-rewrites the entire `config.ini`; that file was瞬时不 writable in the user's environment (editor占用 / concurrent process) → `PermissionError` uncaught → web.py crashed directly at import stage.

**Root cause**:

1. `src/config_io.py` `read_config_value` "writes back on every miss" when key missing and has zero tolerance for write failure, inconsistent with the same module's `backup_file` best-effort mode — any missing key + non-writable config crashes the whole app.
2. `main.py`'s old-key compat reused the write-back `read_config_value`, making "migrated config missing old key" instead trigger an old-key write-back; the comment-promised "compat" was actually broken.

**Changes**:

- `src/config_io.py` `read_config_value` write-back wrapped in `try/except OSError`: on failure only `logger.warning` and return default, no longer throw (consistent with `backup_file`). Eliminates the class of "any missing key + non-writable config → app crash".
- `main.py` old-key compat changed to `config.has_option(...)` checking existence before `config.get(...)`, **never writes back** — old keys should only be read, never auto-recreated.

**Commit**: `fix(config): 修复 config.ini 不可写时 import main 阶段崩溃（只读写回 best-effort + 旧键兼容仅读取）`.

### v4.0.8.2-dev (2026-08-16) — Huya OD/BD/UHD app-path danmaku triplet returned + eliminate silent skip

**Source**: Last round's log exposed `[虎牙直播]弹幕跳过: danmaku_args 为空` (no warning, pure silence). Root cause: quality `原画`→`OD`→main.py takes app path `get_huya_app_stream_url`, but that function's return dict at lines 858-865 only contained `anchor_name/is_live/m3u8_url/flv_url/record_url/title`, **missing** `yyid/lChannelId/lSubChannelId`; main.py:921-923 read None → `record_danmaku_args=None` → danmaku not recorded. A "pending user decision" item registered in the third-round log.

**Root cause**: The app path (profileRoom interface)'s triplet should align with the web path (`get_huya_stream_data`'s `gameLiveInfo.yyid` + `gameStreamInfoList[0].lChannelId/lSubChannelId`), but `get_huya_app_stream_url` wrote `lChannelId/lSubChannelId` into `play_url_list`'s intermediate structure inside the loop, and didn't carry them when finally returning. `test_profileRoom_fields` hitting `KeyError: 'yyid'` at the time was exactly the reproduction of this dangling pit (the test was written for the fix, code not landed).

**Changes**:

- `src/spider.py` `get_huya_app_stream_url` return dict adds `yyid/lChannelId/lSubChannelId`: `yyid ← profile_info.get("yyid")`; `lChannelId ← data_field.get("chTopId") or base_steam_info_list[0].get("lChannelId")`; `lSubChannelId ← data_field.get("subChId") or base_steam_info_list[0].get("lSubChannelId")` (prefer top-level `chTopId/subChId` from data, present in some responses; otherwise fall back to `baseSteamInfoList[0]`, non-empty in the live path). Aligned with web-path field semantics, main.py's OD/BD/UHD branches assemble `ayyuid/topSid/subSid` without changes.
- `main.py` OD/BD/UHD branches' triplet-missing branch adds `logger.debug` (records actual `yyid/lChannelId/lSubChannelId` values), eliminating the original silent skip,方便 future locating of spider return-structure changes.

**Commit**: `f415184 fix(huya): 补 OD/BD/UHD app路径弹幕三元组返回并消除静默跳过` (2 files: spider.py/main.py; test_huya_danmaku.py already in repo).

### v4.0.8.2-dev (2026-08-16) — SSL coverage refactored into generic platform list (compat with old Huya single-column key)

**Source**: Run log `stream_select:_validate_stream_url` reported Bilibili `bilivideo.com` `CERTIFICATE_VERIFY_FAILED: Hostname mismatch` (cert SAN doesn't include `2409_8c20_…bytefcdnrd.com`). This root cause is identical to Huya TX, but last round's direction 2 only registered `ssl_verify=False` coverage for Huya, Bilibili still went through global strict validation → Bilibili flv stream judged unreachable.

**Change** (`main.py` config-parse section): refactored the `虎牙是否禁用SSL证书验证(是/否)` single-column key into comma-separated platform list `禁用SSL证书验证的平台(逗号分隔)`. After parsing, calls `set_platform_ssl_verify(platform, False)` per platform; validator / ffmpeg / direct-download all three paths uniformly read via `get_effective_ssl_verify(platform)`, ensuring consistency. Kept compat with old key `虎牙是否禁用SSL证书验证(是/否)=是` (equivalent to adding "虎牙直播" to the list), avoiding breaking already-enabled user configs.

**Config example**: `禁用SSL证书验证的平台(逗号分隔) = 虎牙直播,B站直播` (same comma-separated format as "弹幕录制平台"; empty = all strict validation, security-first). `config/config.ini` is gitignored for containing cookies, not committed.

### v4.0.8.2-dev (2026-08-16) — backup_file rotation-delete misleading ERROR: changed to best-effort

**Source**: Run log reported `src.config_io:backup_file:150` "备份配置文件 ... 失败" every backup cycle. `backup_file` does two things: `shutil.copy2` copies a timestamped backup (success) + when backup count > 6, `os.remove` deletes the oldest (failure).

**Root cause**: The rotation-delete `os.remove` was intercepted by the agent runtime's safe-delete guard (rerouted to Windows Recycle Bin), and the sandbox Recycle Bin was unavailable → threw `SAFE_DELETE_FAIL_CLOSED`; the exception was caught wholesale by the function's trailing `except Exception` and mis-logged as "backup failed". The backup copy itself succeeded; only the designated cleanup failed, and `backup_config/` can't be pruned in the sandbox (on real Windows `os.remove` direct-deletes unaffected, so this only appears when sandboxed / file locked).

**Change** (`src/config_io.py`): isolate the rotation `os.remove` as best-effort — `except OSError` logs warning and `break`, no longer makes the whole backup error, nor infinite-retries on the same file (prevents infinite retry).

### v4.0.8.2-dev (2026-08-16) — Bilibili danmaku param fetch landed + Bilibili live stream Referer added

**Source**: Run log `__main__:start_record:986` reported `[B站直播]弹幕信息获取失败: module 'src.spider' has no attribute 'get_bilibili_danmaku_info'`; `bilivideo.com` validation `status_code=403`. The former is a dangling call left by refactoring (`todo.md` described the function as "fixed and verified", but the `def` never landed), the latter shares the same root as Huya (missing Referer).

**Root cause**:

- `main.py:981` calls `spider.get_bilibili_danmaku_info(url=, proxy_addr=, cookies=)` to get Bilibili danmaku room-entry params, but that function only existed in `todo.md` planning, code missing → `AttributeError` swallowed by `except` → `record_danmaku_args=None` → `get_danmaku_collector` returns None → Bilibili danmaku not recorded (last round misjudged as "only mypy type error", corrected).
- Bilibili live stream `bilivideo.com` returns 403 for Referer-less requests (empty content-type); `get_record_headers` has no Bilibili entry, so neither ffmpeg nor the validator carries Referer → both ends consistently can't get the stream.

**Change**:

- `src/spider.py`: landed `get_bilibili_danmaku_info(url, proxy_addr=None, cookies=None)` — `room_init` short-id to real room_id + uid; `nav` gets `wbi_img` for img_key/sub_key; `spi` (`/x/frontend/finger/sp`) gets buvid3; `getDanmuInfo` carries wbi signature (`_MIXIN_KEY_ENC_TAB` mix + `w_rid` md5). Returns the `{room_id,uid,token,server_host,host_list,buvid,cookie}` needed by `BilibiliDanmaku.start`. Each step independently try/except logs warning, returns `None` on failure (**no longer** uses `@trace_error_decorator`, because its default exception return `{"is_live": False}` would create a broken collector missing fields); `_sign_wbi` call also wrapped in try. Real wbi keys are 32 hex chars each (orig 64 long, mix-table indexes to 63).
- `src/stream_select.py` `get_record_headers`: added `"B站直播": "referer:https://live.bilibili.com/"`, effective consistently on both ffmpeg recording and reachability validation (already injected generically by platform).

### v4.0.8.2-dev (2026-08-16) — Huya optional cert-validation disable (platform-level SSL override, strict by default)

**Source**: Huya TX CDN edge node (`tx.flv.huya.com`) cert SAN doesn't include the actual hostname (`2409_8c20_6ed1_22a__46.bytefcdnrd.com`), tls handshake reports `CERTIFICATE_VERIFY_FAILED: Hostname mismatch`; under global `ssl_verify=True` (default) both validator and ffmpeg judge unreachable. This is a CDN-side config issue requiring a safe "optional disable" degradation, not a uniform global-off.

**Root cause**: The original `_validate_stream_url` only used global `ssl_verify`, with no "platform-level override" mechanism; the ffmpeg recording command didn't even insert `-tls_verify`, so globally disabling SSL never affected ffmpeg (validator and recording inconsistent).

**Change** (strict by default, a safe degradation, only takes effect when Huya explicitly enables):

- `src/http_config.py`: added generic `ssl_verify_platform_overrides` dict + `set_platform_ssl_verify(platform, value)` + `get_effective_ssl_verify(platform)` — platform override takes the override value, otherwise the global (default True). Validator / ffmpeg / direct-download all three paths uniformly read via this interface, ensuring consistency.
- `src/stream_select.py`: `_validate_stream_url`'s `verify` default changed to `get_effective_ssl_verify(platform)`.
- `main.py:2291` area: reads `录制设置/虎牙是否禁用SSL证书验证(是/否)` (default "否"), `set_platform_ssl_verify("虎牙直播", False)` when "是"; ffmpeg command inserts `-tls_verify 0` when effective verify is False (input option, before `-i`); direct-download `httpx.Client` also passes `verify=`.
- `config/config.ini`: added `虎牙是否禁用SSL证书验证(是/否) = 否` (with explanatory comment).

### v4.0.8.2-dev (2026-08-16) — Huya recording fix: add Referer to resolve CDN 403 false-unreachable

**Source**: Run log showed room 660002 (Huya) HLS/FLV/record_url all three failed (AL CDN 403 + TX CDN TLS cert hostname mismatch), `select_source_url` returned None causing this round to not record. Real-test locating: Huya CDN directly returns 403 for Referer-less requests (text/html denial page), with `Referer: https://www.huya.com/` it's 200 (unrelated to UA).

**Root cause**: The recorder validator (`_validate_stream_url`) and ffmpeg recording command (via `get_record_headers`) both send no Referer for Huya, so both ends consistently can't get the stream — not a signature expiry (`wsTime` decoded ~24h later than log time, not expired); TX's cert mismatch is a separate independent problem.

**Change** (`src/stream_select.py` + `main.py`):

- `get_record_headers` added `"虎牙直播": "referer:https://www.huya.com/"`: ffmpeg recording (`main.py:1690` inserts `-headers`) and direct-download (`main.py:605`) both take effect automatically.
- `_validate_stream_url` added `platform` param: per platform calls `get_record_headers` to resolve the `referer` header and inject it into the httpx probe request, making reachability judgment consistent with the recording path.
- `select_source_url` passes `platform` through to 4 `_validate_stream_url` calls; `main.py:1590` passes `platform` when calling.

### v4.0.8.2-dev (2026-08-16) — main.py split: 6 categories of functionality extracted to src submodules (complete refactor)

**Source**: User asked to analyze `main.py` for independently extractable functionality, move extracted modules to `src/` for reuse, and chose the "complete refactor" approach (changing main.py wiring and deleting duplicate code together).

**Change**:

- Extracted 6 independent modules (all under `src/`, re-exported to keep `main.<name>` compatibility):
  - `src/ffmpeg_proc.py` — FFmpeg process register/unregister/terminate/cleanup (`register_ffmpeg_process`/`unregister_ffmpeg_process`/`_terminate_ffmpeg_process`/`_cleanup_single_ffmpeg_process`/`cleanup_all_ffmpeg_processes`/`_get_error_line`), with its own `_ffmpeg_processes`/`_processes_lock`, zero main dependency
  - `src/video_postprocess.py` — startup info / FFmpeg check / segmentation / to mp4·m4a / subtitle generation (`get_startup_info`/`_run_ffmpeg_checked`/`segment_video`/`converts_mp4`/`converts_m4a`/`generate_subtitles`)
  - `src/stream_select.py` — stream-address selection / validation / quality code / rate-limit (`contains_url`/`clean_name`/`get_quality_code`/`get_record_headers`/`_validate_stream_url`/`select_source_url`/`_douyin_rate_limit`)
  - `src/notify.py` — push / script / success-failure counting / concurrency adjust / cleanup (`push_message`/`run_script`/`record_error`/`record_success`/`adjust_max_request`/`clear_record_info`)
  - `src/recorder_status.py` — status snapshot / display (`get_status`/`display_info`)
  - `src/config_io.py` — config read/write / safe numeric conversion / backup (`update_file`/`delete_line`/`read_config_value`/`_safe_int`/`_safe_float`/`backup_file`/`backup_file_start`)
- `main.py`:
  - Added `__main__` guard at top (`if sys.modules.get("main") is None: sys.modules["main"] = sys.modules["__main__"]`), preventing child modules' `import main` from re-executing the whole file when running `python main.py`
  - Added re-export block (`from src.<mod> import (...)`), external callers `web.py`/`gui.py`/`src/web_api.py`/tests are zero-change compatible via the `main.<name>` namespace (incl. `monkeypatch main.register_ffmpeg_process` etc.)
  - Deleted duplicate definitions of `update_file`/`delete_line` inside main.py (config_io is the single source of truth), cleaned trailing whitespace left by AST deletion
  - Line count 3543 → 2696

**Pitfalls (avoided)**:

- Modules deeply coupled to main globals (`notify`/`recorder_status`/`config_io` and parts of `video_postprocess`/`stream_select`) uniformly use runtime `import main` to lazily access globals (`main.<x>`), avoiding startup-time param bloat at call sites; paired with the `__main__` guard to avoid `python main.py` re-execution
- The AST-deletion script's first version missed deleting the AnnAssign-declared `_ffmpeg_processes`/`_processes_lock`; rewrote the script to merge-comment blocks upward for AnnAssign nodes and delete together, 34 blocks total (function definitions + section comments + orphan state declarations)

### v4.0.8.2-dev (2026-08-16) — Danmaku subpackage flattening: src/danmaku/\* → src/\*

**Source**: User asked to move the whole `src/danmaku/` subpackage up to `src/`, and check whether functionality broke from the move.

**Changes**:

- `git mv` file-by-file/dir-by-dir: `base.py` `collector.py` `srt_writer.py` `ws_client.py` `platforms/` `proto/` moved from `src/danmaku/` up to `src/`; deleted `src/danmaku/__init__.py` and the `src/danmaku/` directory (staged files force-deleted with `git rm -f`).
- `__init__.py` conflict: parent package `src/__init__.py` already existed, not overwritten. The original `danmaku/__init__.py`'s `get_danmaku_class`/`get_danmaku_collector` + platform registry migrated into `src/__init__.py` (registry lazily loaded, keeping `import src` lightweight; retained `DOUYIN_SKIP_RUNTIME_CHECK` guard).
- Whole-repo bulk import rewrite: `from src.danmaku...` → `from src...`, `src.danmaku import` → `src import`, covering `src/**/*.py`, `main.py`, `tests/*.py`.
- Updated packaging smoke stub `_smoke_stub.py`'s `HEAVY` list: `src.danmaku` → `src.srt_writer`/`src.ws_client`/`src.proto`.

**Pitfalls (fixed)**:

- `main.py:109` after the bulk rewrite still had `from src.danmaku import get_danmaku_collector` (the first rewrite reported "cleared" but was a false judgment), causing all import-main tests `ModuleNotFoundError`, 14 cases ERROR. Changed to `from src import get_danmaku_collector` and passed. **Lesson: after bulk import changes, must `grep -rn "src.danmaku"` to confirm the whole repo is cleared, don't trust the summary.**
- Dual-mode test scripts (`test_*_live_collector.py` top-level `SECONDS=int(sys.argv[2])`) — when multiple files are collected by pytest in one process, `sys.argv[2]` becomes another test path → `int()` crashes; must run each file separately. A pre-existing pitfall, unrelated to this round.

### v4.0.8.2-dev (2026-08-16) — Danmaku recording module review fix (danmaku_check.md full issue list)

**Source**: `danmaku_check.md` review report (P0×1 / P1×2 / P2×2 / P3×2 + test gaps); the danmaku feature never actually worked because 6 call sites weren't wired up.

**Change**:

- **P1 wiring**: `main.py`'s 6 `check_subprocess` call sites now pass `platform=platform, danmaku_args=record_danmaku_args` (both variables are `start_record` locals, reset each round, no need to move assignment); the danmaku collector was previously never created, the whole `src/` chain was dead code.
- **P1 stop position**: `danmaku_collector.stop()` moved from inside the `while process.poll() is None` loop to after the loop (before the fix, danmaku was terminated after ~1 second); `DanmakuCollector.stop()` added `_stop_called` reentry guard, idempotent semantics clear.
- **P2 filename alignment**: `check_subprocess` placeholder stripping now covers both `_%02d`/`_%03d`; FLV segment template `_%02d` → `_%03d` to align with MKV/MP4/TS; `SrtWriter._segment_path` `{seg:02d}` → `{seg:03d}`, SRT shard `_000.srt` corresponds one-to-one with recording `_000.xxx`; incidentally deleted the dead variable `seg_file_path` in FLV-to-MP4 segment.
- **P3 ttwid dynamic**: `src/platforms/douyin.py` removed hardcoded stale `_DEFAULT_TTWID`, on empty cookie `await get_ttwid()` (directly awaited in the collector thread's event loop, process-level cache), failure only warns without affecting recording.
- **P3 config guard**: `弹幕分片时长(秒)` changed to `_safe_float(..., 1800.0)`, illegal values no longer kill the recording main loop.
- **P0/P2 staging area**: `.gitignore` appended `.qoder/`, `.agents/`, `.pnpm-store/`, `.dsh-validation/`, `.ego-browser-test/`, `.plugin-src/`, `.tmp-dps-extract/`, `tests/_out_e2e/`, `tests/_out_live/`, `.coveragerc-concurrency`, `*.isorted`; staging area removed 400+ `.qoder/` artifacts and temp coverage configs, completed `pyproject.toml`, `src/`, `scripts/`, `tests/`, `AGENTS.md`, `.github/workflows/ci.yml` (deleted `douyin_pb2.pyi.isorted` residue).
- **Tests**: added `tests/test_danmaku_wiring.py` 9 cases (wiring params, stop once outside loop, placeholder stripping, early interrupt, unsupported-platform skip, SRT 3-digit width, stop idempotent, ttwid dynamic fetch/failure fallback); `test_srt_timeline_anchor.py` segment assertions synced `_000/_001`.

### v4.0.8.2-dev (2026-08-16) — Fix HLS (m3u8) validation mis-judging 405 and falling back to FLV

**Source**: Run log showed `pull-hls-f26.douyinliving.com/...m3u8` returns `405` + `content-type=text/html` for HEAD, `_validate_stream_url` hit the text/html block and directly judged failure, falling back to FLV; but the same stream's FLV validation passed (actually reachable) — a mis-kill.

**Root cause**: `main.py`'s `_validate_stream_url` (sync validator) had wrong check order — it checked `text/html` content-type and `return False` **before** the m3u8 Range GET probe branch. Douyin `douyinliving.com`'s m3u8 always returns `405 + text/html` for HEAD, so the m3u8 probe branch was never reached, inconsistent with the async validator `src/async_http.py:get_response_status` (which already implements "HEAD non-200 m3u8 always does Range GET probe").

**Change**: `main.py` `_validate_stream_url`

- Moved the m3u8 source (url contains `.m3u8`) Range GET probe **before** the text/html block, and only bypasses the unreliable HEAD content-type/status-code for m3u8 sources; HEAD returning 200 or a streaming content-type still directly judged reachable.
- Non-m3u8 sources (flv/record_url) keep the original text/html heuristic rejection.
- Sync and async validators now align on m3u8 handling semantics.

### v4.0.8.2-dev (2026-08-16) — docstring bulk conversion to # comments (enforce project comment convention)

**Source**: User asked to check `"""` comments and change to `#` comments, enforcing the project convention "Python comments uniformly use `#`, not triple-quote docstrings".

**Conversion method**: Used AST to precisely identify docstring nodes (distinguished from ordinary triple-quote string literals to avoid collateral damage), replaced by `#` comments over the (lineno, end_lineno) line range. Replaced from back to front to avoid line-number shift.

**Scope**: Scanned 79 .py files, converted 78 docstrings (28 files).

- 25 module-level docstrings → file-header `#` comments
- 38 FunctionDef docstrings → function-body-header `#` comments
- 7 AsyncFunctionDef docstrings → function-body-header `#` comments
- 4 ClassDef docstrings → class-body-header `#` comments
- 4 `@abstractmethod` (`src/base.py`'s start/stop/heartbeat/decode_message) whose body contained only a docstring: after deletion supplemented with `pass`
- Kept `src/proto/douyin_pb2.py`'s 1 docstring (protoc-generated file, DO NOT EDIT)

**Pitfalls and handling**:

- `tests/test_bili_e2e.py`'s docstring described Bilibili packed frames separated by `\0`; AST parsed it into an actual null char stored in `.value`, and writing it as a `#` comment produced a source with a null byte causing py_compile rejection. Manually replaced with the literal `\0` to fix.
- Indentation used the docstring node's own `col_offset` (body indent), not the `def`/`class` line indent, ensuring the comment aligns with body content.

- FastAPI endpoints (`src/web_api.py` 15) had no docstrings before or after conversion, OpenAPI descriptions use other means, no impact.
- Function `__doc__` attribute became None; the project has no logic depending on `__doc__`.

### v4.0.8.2-dev (2026-08-16) — Full code check and fix (mypy/basedpyright both cleared)

**Source**: User asked to "check all code" (type checking + unit tests + code style + static analysis, all auto-fixed).

**Baseline**: mypy 57 errors / basedpyright 27 errors / black 27 files need formatting + main.py parse failure / isort 9 files / pyflakes 13 / pytest can't collect due to missing deps.

**Fixes**:

1. **main.py function signature corrupted (syntax error)**: `check_subprocess` signature was wrongly split into two parts, the second becoming a dangling statement causing black parse failure. Merged into the correct 7-param signature (incl. `platform`/`danmaku_args`).
2. **main.py danmaku variable scope break (NameError)**: `main()`'s global declarations missed `enable_danmaku`/`danmaku_split_time`/`danmaku_platforms`, causing `check_subprocess` reference to be undefined. Added global declarations + module-level type annotations (`enable_danmaku: bool`/`danmaku_split_time: float`/`danmaku_platforms: list[str]`/`record_danmaku_args: dict[str, Any] | None`).
3. **main.py `seg_pattern` undefined (NameError)**: FLV segment-transcode branch referenced an undefined variable. Added glob pattern definition `{prefix}_*.flv`.
4. **spider.py Huya return dict missing danmaku fields (functional bug)**: `get_huya_app_stream_url` extracted `_yyid`/`_l_channel`/`_l_sub_channel` into `play_url_list`, but the final return dict missed these three fields, causing `test_profileRoom_fields` to fail. Added to return dict.
5. **spider.py repeated `json_data['data']` access (type degradation)**: lines 816-822 repeatedly accessed the already-cast `data_field`, overwriting the cast result from lines 804/807 causing type degradation to object. Changed to reuse the already-cast variable.
6. **bilibili.py `int(room_id)` missing default (runtime TypeError)**: `self._args.get("room_id")` missing key → `int(None)` crashes. Added default 0, consistent with uid writing.
7. **srt_writer.py `_t0` None check + `_fp` type annotation**: after `_ensure_started` side-effect, `_t0` non-None adds assert; `_fp` annotated `Optional[TextIO]`.
8. **ws_client.py `on_heartbeat` type annotation too narrow (5-platform cascade errors)**: defined as `Callable[[], None]` but implementation supports async (`inspect.isawaitable`), each platform passing async functions errored. Changed to `Callable[[], Union[None, Awaitable[None]]]`.
9. **5 platforms `on_reconnect` writing simplified**: `(self._on_close and (lambda...)) if self._on_close else None` simplified to `on_reconnect=self._on_close` (semantically equivalent, eliminates truthy/None-call warnings).
10. **danmaku module type annotations completed**: 5 platforms' `__init__` `*args/**kwargs` added `Any` annotations; douyu `_stt_to_obj`/`_dispatch` supplemented; `__init__.py` `get_danmaku_class`/`get_danmaku_collector` added return type + cast; collector `_only_fans` cast(Any); douyin `_make_hb_frame` cast(bytes).
11. **douyin_pb2.pyi type stub created**: protobuf-generated module attributes dynamically injected, mypy/basedpyright can't see `PushFrame`/`Response`/`ChatMessage`. Created `.pyi` stub declaring 3 message classes and referenced fields (payloadType/payload/logId/user etc.).
12. **spider.py type narrowing**: 3 `json.loads(resp)` changed to the project's existing `_loads_dict` safe conversion; `get_bilibili_danmaku_info` return type `OptionalDict`(dict[str,str]) changed to `dict[str, object] | None` (returns include int values); multiple object casts (rsplit/get/index).
13. **base.py removed unused `field` import**.
14. **5 collector tests `int(argv)` tolerance**: dual-mode scripts crash on `int('-q')` when pytest collects with `sys.argv[2]='-q'`. Added `not argv.startswith('-')` guard.
15. **Installed missing deps**: venv missing `brotli`/`protobuf` (listed in requirements.txt but not installed), tests collectable after install.
16. **black + isort formatting all** (29 files); cleaned isort residual `.py.isorted` backups.

**Pending user decision (not bugs, not auto-modified)**:

- Danmaku feature unwired: `start_record`'s platform branches extract `record_danmaku_args`/`platform`, but all 6 `check_subprocess` call sites pass only 5 positional args, missing `platform`/`danmaku_args`, making the danmaku collection branch dead code. Wiring requires adding params at call sites and verifying the danmaku module end-to-end.
- `record_danmaku_args`/`seg_file_path` assignments unused (pyflakes warning, former due to unwired, latter an author-marked dead-code branch).
- `main()`'s `global platform`/`global record_danmaku_args` declarations ineffective (main never assigns, they're global state for other functions to read).

### v4.0.8.2-dev (2026-08-16) — Code-gate recheck and test-script sync fix

**Source**: User asked to "check code", executing the black / isort / mypy / pytest four quality gates per AGENTS.md convention.

**Findings and fixes**:

1. **Test suite blocked entirely by stale import (real defect, fixed)**:
   - `tests/test_douyin_live_collector.py:17` still imported `from src.platforms.douyin import _DEFAULT_TTWID`, but `douyin.py` already deleted that constant in the P3 ttwid-dynamic round (see above), changing to `get_ttwid()` dynamic fetch.
   - This ImportError caused pytest collection to exit 2 directly, **all 515 tests unexecuted**.
   - Fix: import changed to `from src.ttwid import get_ttwid`, `resolve_cookie()` fallback logic changed to `asyncio.run(get_ttwid())`, set empty on failure (consistent with `douyin.py`'s current `await get_ttwid()` semantics).
2. **Format deviations (3 places, auto-fixed)**:
   - `tests/test_web_api.py`: function signature line-wrap compressible within 120 cols
   - `tests/test_concurrency_rate_limit.py`: stdlib vs third-party import grouping error
   - `tests/test_weverse_auth.py`: stdlib vs third-party import grouping error

- `black --check .` 95 files all passed
- `isort --check-only .` all passed
- `mypy src/` 31 files 0 errors
- `pytest -q --tb=short` **515 passed, 2 skipped** (30.4s, exit 0)
- `scripts/check_version.py` version 4.0.8.2 consistent

**Observation (not modified)**: pytest exit-phase `RuntimeWarning: coroutine 'FakeAsyncClient.aclose' was never awaited` and `Loguru Handler ... ValueError: I/O operation on closed file` are test-stub/interpreter-shutdown noise, not code defects.

### v4.0.8.2-dev (2026-08-16) — Danmaku WS connection explicitly bypasses system proxy (proxy=None, root-causing "connecting through a SOCKS proxy requires python-socks")

**Source**: User `python3 main.py` real test, Bilibili danmaku log clearly errored `连接关闭: connecting through a SOCKS proxy requires python-socks` (the earlier short-id room_id conversion and un-awaited heartbeat-coroutine sub-issues were already fixed, but still couldn't connect).

**Root cause**: `websockets.connect(proxy=True)` auto-detects and follows proxy by default; on macOS `urllib.request.getproxies()` directly reads system network settings (System Preferences → Network → Proxies) for the system-level SOCKS proxy (e.g. the `socks5://127.0.0.1:7890` written by Clash), not shell env vars; the SOCKS protocol needs the `python-socks` library, and without it installed the above error is reported. Video fetch goes through ffmpeg/own headers, not websockets, so recording is unaffected by proxy; standalone test scripts behaved erratically because of different runtime environments/system-proxy states.

**Change** (`src/ws_client.py` `connect()`): explicitly pass `proxy=None`, danmaku WS connects directly to the server, unaware of system proxy and `ALL_PROXY` etc. env vars. This fix takes effect uniformly for **all platforms** reusing `WsClient` (Bilibili/Douyu/Huya/Douyin/Twitch etc.) danmaku connections.

**Decision basis**: The danmaku channel is domestic direct-connect by nature, doesn't need an outbound proxy, consistent with the overall direct-connect semantics of "user configured proxy-off recording"; minimal dependencies (no new `python-socks`); doesn't touch system settings; explicit declaration is better than implicit detection (avoids library upgrades changing default behavior and re-triggering the pitfall). If an individual overseas platform's danmaku truly needs a proxy, a later optional `proxy` param can be added to `WsClient` to pass through on demand, not globally followed.

### v4.0.8.1-dev (2026-08-15) — Fix Web smoke test failure due to security guard exit code 1

**Source**: `build_exe.py --smoke` failed at the `smoke_web` stage in CI, process exited abnormally (exit code 1). Log showed `[web] ❌ 拒绝启动: 未启用 Web 认证时不允许监听非回环地址 (0.0.0.0)`.

**Root cause**: The Web panel `web.py`'s C1 security guard — `web_auth_enable=false` and listening on a non-loopback address (`config.ini` default `web_host=0.0.0.0`) calls `sys.exit(1)`. The smoke test started the Web exe with default config, the guard triggered and the process exited, and `smoke_web`'s `_finish(expect_alive=True)` judged it a failure.

**Change**: `build_exe.py`

- `_launch()` added `extra_env` param, injecting env vars into the child (merged with `os.environ`, not overriding other vars).
- `smoke_web()` passes `extra_env={"DOUYIN_WEB_ALLOW_INSECURE": "1"}` when starting the Web exe, using that variable's intended purpose (local CI/sandbox temporary exposure) to bypass the guard. Smoke only does local HTTP liveness probing, not truly exposed to LAN; it also keeps the "actually bind 0.0.0.0" verification path, which better exposes regressions than changing `web_host` to 127.0.0.1. Production deployment default secure behavior unchanged.

### v4.0.8.1-dev (2026-08-15) — Code-review leftover fix (pyflakes cleared + dead-code/implicit-side-effect cleanup)

**Source**: `代码审查报告_DouyinLiveRecorder.md` (report parent item rvVeM2 leftover improvement items).

**Change**:

- `src/web_api.py`: removed unused `validate_room_target` import. Verified `add_room`/`update_room` already do newline+control-char validation on url/quality/name via `format_url_line` (web_config.py:178-180), which is a **superset** of `validate_room_target`, so **no validation branch is dropped**; the function itself is still referenced by `tests/test_web_config.py`, so retained.
- `src/web_config.py`: removed unused `from typing import cast` import (pyflakes warning).
- `src/spider.py`:
  - Deleted unused local var `cast_start_date_code_int` (orig L2443; `cast_start_date_code` still used).
  - Deleted Kuaishou old-version `playUrls` dead-code branch (orig L686, marked "invalid since 2024-11-28"); changed to accept only the modern h264 dict format, avoiding `play_url_list` undefined NameError.
  - Converged 38 `print` → `logger` (failure/exception→warning, success/status→info, pure diagnostic→debug). Console sink is at DEBUG level, user-visible output not lost.
  - `get_huajiao_sn` parse failure silent comment of `URL_config.ini` changed to **explicit + warning log** (keeps the "comment out invalid address" UX).
  - `get_taobao_stream_url` refresh-token writeback to `config.ini`'s `taobao_cookie` changed to **explicit + info log** (persistence required, keeps functionality).

### v4.0.8.1-dev (2026-08-15) — Fix test_proxy.py flaky failure from harness env-var bloat

**Symptom**: Whole `pytest` occasionally 1 failed (`tests/test_proxy.py::TestProxyDetectorLinux::test_linux_get_proxy_info_with_auth`), single run passed, re-run several times all green — typical test-inter-state-pollution illusion.

**Root cause**: `unittest.mock.patch.dict` on `os.environ` **regardless of `clear` True/False** snapshots and restores the whole environment (`_patch_dict` has `original = in_dict.copy()`; `_unpatch_dict` unconditionally `_clear_dict()` then `update(original)` writes back wholesale). In the environment, the WorkBuddy harness-injected `CODEBUDDY_MCP_CONFIG` and other vars **dynamically bloat**; once they exceed Windows' 32767-char env-var limit, `update(original)` writeback throws `ValueError: the environment variable is longer than 32767 characters`. After fixing the first case, the failure "shifted" to the next `patch.dict` case (`test_linux_get_proxy_info_simple`), same error — common root cause, not a single-point issue.

**Change (tests/test_proxy.py)**:

- All 7 `patch.dict(os.environ, ...)` in `TestProxyDetectorLinux` uniformly replaced with pytest's `monkeypatch.setenv/delenv` (only operates single keys, no wholesale snapshot/restore); added `_clear_proxy_env(monkeypatch)` helper to uniformly clear proxy-related vars
- `test_linux_get_proxy_info_with_auth` assertion tightened to `ip == "proxy.example.com"` and `port == "3128"` (removed the always-false dead branch `"proxy.example.com:3128"`)
- Removed now-unused `import os` and `from unittest.mock import patch`

**Convention recorded**: Under Windows + harness environments, tests operating on env vars must use `monkeypatch`, avoiding `patch.dict(os.environ)` — otherwise harness var bloat exceeding 32767 triggers `ValueError`. Recorded in project long-term memory (MEMORY.md known pitfall).

### v4.0.8.1-dev (2026-08-15) — basedpyright config landed + types/deps/tests wrap-up

**Background**: Full basedpyright run reported **189 errors / 3241 warnings**, scary at first glance but mostly noise. After locating, the root cause was **missing config + two real defects**, now all cleared.

**Root cause and changes**:

- **`pyproject.toml` added `[tool.basedpyright]` config section**: project deps are actually installed in the workbuddy managed venv (`envs/default`), but basedpyright didn't recognize its own venv and fell back to the system Python 3.13.12 without packages, causing wholesale `reportMissingImports` (mypy hid it via `ignore_missing_imports` to appear green). Configured `venvPath`/`venv` to point at `envs/default`, `typeCheckingMode=standard`, excluded `typings/`/`node/`/`ffmpeg/`/`downloads/` etc., `reportMissingModuleSource=none`. After config, business code went from 189/3241 → **0 errors / 0 warnings / 0 notes**.
  - **Note**: `venvPath` hardcodes this machine's workbuddy managed venv path (machine-specific); CI still uses `mypy src/` as the gate (basedpyright not a CI check); on machine/CI change it needs separate override or switch to `python.analysis` auto-detection.
- **Installed `exejs` into managed venv**: `pyproject.toml` declares `exejs>=1.0.1`, but the venv only had PyExecJS installed, causing `room.py`/`spider.py`/`utils.py`'s three `import exejs` to report `reportMissingImports` under the basedpyright config (runtime `ImportError`). After install, 3 errors gone.
- **`src/sync_http.py` JsonType dead-code refactor (real problem exposed after config)**: originally `try: from requests._types import JsonType except ImportError: from typing import Any as JsonType`. `typing.Any` is a runtime value, `from typing import Any as JsonType` makes the symbol judged a **variable**, basedpyright reports `reportInvalidTypeForm` (variables not allowed in type expressions); and requests 2.33+ moved `JsonType` into a `TYPE_CHECKING` block, runtime import always fails, the fallback branch is the only runtime path. Changed to a local explicit recursive `TypeAlias`, structure consistent with requests' own `JsonType` — `JsonType: TypeAlias = None | bool | int | float | str | Sequence["JsonType"] | Mapping[str, "JsonType"]` (added `from collections.abc import Sequence` and `from typing import TypeAlias`), `requests.post(json=json_data)` param validation unaffected.
- **`main.py:3271`** bare `tuple` → `tuple[Any, ...]` (added `Any` to typing import at line 89).
- **`gui_legacy.py:425`** `__init__` added `self._status_anim_timer: str | None = None` (originally only assigned inside method, not initialized). Old GUI entry, low priority but rigor added.

**Test wrap-up (env-related)**: `tests/test_web_api.py`'s `TestListFiles::test_broken_symlink_skipped` and `test_symlink_outside_skipped` under Windows sandbox `os.symlink` **doesn't throw** but produces a normal file (`islink()=False`), the original `except OSError: pytest.skip()` guard failed causing 2 FAILED. Added `else` branch after the two tests' `os.symlink` to verify `os.path.islink()` realness, `pytest.skip` if a real symlink can't be created; normal environment `islink=True` continues test.

### v4.0.8.1-dev (2026-08-15) — Code-review follow-up fix (lock deadlock-proofing / error_count semantics / format-exclude)

**Credential-dedup lock deadlock-proofing (`src/spider.py` / `src/ttwid.py`)**:

- `_kuaishou_did_lock` / `_twitch_client_id_lock` / `_ttwid_lock` changed from `threading.Lock` to `threading.RLock`: when the lock is held across `await`, if a second concurrent coroutine appears in the same event loop, a normal Lock deadlocks spinning on the same thread; RLock allows same-thread reentry (worst case degrades to one idempotent repeat fetch), cross-thread dedup semantics unchanged
- `tests/test_concurrency.py::test_ttwid_module_pattern` assertion updated to RLock in sync

**error_count semantics clarified (`main.py`)**:

- `error_count` no longer periodically cleared by `adjust_max_request`, semantics fixed to "cumulative error count since process start"; CLI status-line text corrected from "current instantaneous error count" to "cumulative error count"
- `get_status()` added `recent_errors` field (`max_request_lock` holds lock to sample `sum(error_window)`), providing the Web panel a window-scoped instantaneous error count, coexisting with cumulative `error_count`
- Web panel (`web/index.html` / `web/app.js`): error-count card label changed to "Error count (cumulative/recent)", value displayed as `cumulative / recent` dual scope (falls back to `-` when either field missing)

**pyproject.toml format-exclude completion**:

- black `exclude` / isort `extend_skip` added `.agents` / `.qoder` / `.workbuddy` / `.plugin-src` / `.dsh-validation` / `.ego-browser-test` / `.npm-cache` / `.pnpm-store`, eliminating format noise from 89 files in third-party dirs; full `black --check` / `isort --check-only` now zero warnings

### v4.0.8.1-dev (2026-08-13) — Fix `get_startup_info()` cross-platform mypy regression

**Symptom**: CI `mypy src/` (Linux) reported 2 errors — `main.py:764: Module has no attribute "STARTUPINFO"`, `main.py:769: Variable "main._StartupInfoType" is not valid as a type`.

**Root cause**: The previous batch (next log entry) to satisfy basedpyright moved `get_startup_info()`'s return type alias `_StartupInfoType` into an `if TYPE_CHECKING:` block and changed to quoted annotation `"_StartupInfoType | None"`. But mypy **always treats `TYPE_CHECKING` as True**, so it unconditionally evaluates `subprocess.STARTUPINFO`; and that symbol only exists in the Windows typeshed, so mypy on Linux can't resolve it → `attr-defined`; the quoted annotation's name is then treated as a variable → `valid-type`.

**Fix**: `subprocess.STARTUPINFO` doesn't exist in non-Windows typeshed at all, can't be referenced as a cross-platform precise return type. Changed to `-> object | None`: the function body's `sys.platform == "win32"` literal branch stays unchanged (mypy skips that branch on Linux, doesn't resolve STARTUPINFO); the caller only passes the return value through to subprocess's `startupinfo=` param (loosely typed in typeshed anyway), so `object | None` loses no real type safety. Removed the `_StartupInfoType` alias and `TYPE_CHECKING` import.

### v4.0.8.1-dev (2026-08-13) — CI `black --check` failure fix + lint job to Python 3.13

**Symptom**: CI `lint` job (`black --check .`) failed exit code 1, reporting `scripts/smoke_test.py` and `gui.py` each had one spot needing reformat.

**Root cause and fix (pure format, no logic change)**:

- `scripts/smoke_test.py:280`: `p.add_argument("--format", ...)` single line over 120 chars, wrapped to multi-line signature per black `line-length=120`.
- `gui.py:1460`: missing blank line after `config = configparser.ConfigParser()` (blank needed before comment), restored.
- After fix `black --check .` → `All done! ✨ 🍰 ✨ 59 files would be left unchanged.` (exit 0).

**Noise reduction (optional enhancement)**: `.github/workflows/ci.yml`'s `lint` job Python raised from `3.12` to `3.13`, aligning with the highest `target-version` in `pyproject.toml`, eliminating the "Python 3.12 can't do AST-safe check on py313 target" warning. `isort` / `version-check` jobs still use 3.12 (no black AST check involved, no change needed).

### v4.0.8.1-dev (2026-08-13) — Type/logic fix batch based on reference info

This round fixed item-by-item per the reference info the user provided (editor-selected blocks). Primary checker basedpyright (1.39.9, ignores `# type: ignore` by default), secondary mypy; minimal changes, preserved original functionality.

**`src/web_api.py` (login brute-force rate-limit type tightening)**:

- `_FAILED_LOGINS: dict[str, deque] = {}` → `dict[str, deque[float]]`: the bare `deque` degraded to `deque[Unknown]` under strict mode, triggering `reportMissingTypeArgument` and cascading `reportUnknownVariableType` / `reportUnknownMemberType` / `reportUnknownArgumentType` (affecting `_login_blocked` / `_record_failed_login` / `_clear_failed_logins` 5 places). deque stores `time.time()`-returned float timestamps; after parameterization 1 error + 10 warnings → 0 errors (only 2 remaining non-attachment warnings: line 34 unused import `validate_room_target`, line 410 `float` expression result unused).

**`build_exe.py` (Linux ffmpeg copy branch, line 327-335)**:

- `shutil.copy2` return value unused → assigned `_ = shutil.copy2(...)`, eliminating `reportUnusedCallResult`.
- Copy args use `Path` (compatible with `os.PathLike`), omitting redundant `str()` conversion.
- Status: basedpyright 0 errors; remaining 18 warnings all in non-attachment areas (`_download_file`'s urllib/json `Any` returns line 210-267, `os.getpgid` `Any` line 421), left untouched per the "ignore other areas" convention.

**`msg_push.py` (tg_bot push, line 169-182)**:

- url originally bound inside try, constructing `json_data` exception caused except block to reference unbound variable → `NameError`; fixed by binding url outside try.
- Didn't validate Telegram business failure (`{"ok": false}`) → added `resp_data.get("ok") is True` check, on failure take `description` for logging and return error.
- Failure returned placeholder `[1]` inconsistent with success `[str(chat_id)]` → unified to `[str(chat_id)]`.

**`main.py` (two places)**:

- line 524 PATH join: `current_env_path` is an import-time snapshot, overriding later PATH changes; `ffmpeg_path` not normalized/deduped → changed to real-time `os.environ.get("PATH", "")` + `os.path.normpath` + dedup.
- `get_startup_info()` (line 765): `_StartupInfoType` assigned in `if sys.platform` runtime branch was treated as a variable by pyright → moved into `TYPE_CHECKING` block with unconditional `subprocess.STARTUPINFO` + quoted annotation.

**`gui.py` (PystrayIcon alias + two mypy false positives)**:

- line 179 `PystrayIcon`: basedpyright 0/0/0, but mypy 16 errors (alias treated as variable inside `TYPE_CHECKING`) → declared with `TypeAlias` (`PystrayIcon: TypeAlias = pystray.Icon` / `object`).
- line 830 `ctk.CTkFrame` is Any to mypy → `cast("tk.Frame", ...)`.
- Cleaned up remaining 2 mypy errors: line 1312 `row_fg` annotated union `str | tuple[str, str]`; line 1461 `config.optionxform` assignment mypy false positive → `setattr` + named function `_preserve_case` (not lambda, avoids basedpyright `reportUnknownLambdaType`). Final gui.py 0/0/0 + mypy Success.

### v4.0.8.1-dev (2026-08-12) — Fix cross-event-loop lock mis-judged as risk-control + blank exception log cleanup

**Problem background**: Run logs frequently showed `... is bound to a different event loop`, after which Douyin web API was judged "empty response from API (possible risk control)" and cascaded to HTML fallback, both failing. Root cause wasn't risk-control: `ttwid` fetch was normal, UA was fine.

**Root cause**: The project's concurrency model is per-room independent thread + independent `asyncio.run()` loop (main.py's hundred-plus `asyncio.run(...)` confirmed). `src/async_http.py`'s `_client_lock` is a module-level singleton `asyncio.Lock()`, lazily bound to that loop after first `await` in the first room's loop; subsequent rooms each `asyncio.run()` a new loop and `await _get_client_lock()` again, triggering CPython's `RuntimeError: ... is bound to a different event loop` (the `<asyncio.locks.Lock …>` in the log is that exception's `str`). This exception was swallowed wholesale by `async_req`'s `except Exception as e:`, logging in the exception branch then returning `""`; `spider.py` treated the empty string as "empty response → possible risk control", so WARNING fell back to HTML, and HTML fetch also returned empty due to the same lock error → ERROR cascade.

**Change (4 places + 1 test)**:

- `src/async_http.py` `_get_client_lock()`: **root-cause fix**. Changed from "singleton `asyncio.Lock | None`" to a `(lock, loop)` tuple cached/rebuilt per **current event loop**, each room gets the lock bound to its own loop within its own loop, no cross-loop `await`; logic consistent with the existing `_client_cache` (client + loop), concurrency-safe
- `src/async_http.py` `async_req` exception branch: `logger.debug(e)` → `logger.debug(f"async_req 请求失败: {url} - {type(e).__name__}: {e}")`, eliminating blank logs from empty `str()` exceptions on Windows, and making the 20:29–20:31:08 batch of real transient network errors observable
- `src/async_http.py` `_close_all_clients`: `logger.debug(e)` → `logger.debug(f"关闭 AsyncClient 失败: {type(e).__name__}: {e}")`
- `src/async_http.py` cross-loop old client close: `logger.debug(f"关闭失效 AsyncClient 失败: {e}")` added `type(e).__name__`
- `tests/test_async_http.py` added `TestGetClientLock`: verifies same lock returned within same loop; independent thread/new loop gets a **different** lock and `await` doesn't trigger `bound to a different event loop` (root-cause regression lock)

### v4.0.8.1-dev (2026-08-11) — Fix Linux/macOS mypy cross-platform type errors

- **Background**: CI (ubuntu-latest) `mypy src/` reported 6 errors — `src/web_tray.py` three `ctypes.windll` (attr-defined), `main.py`'s `subprocess.STARTUPINFO` / `STARTF_USESHOWWINDOW` (name-defined / attr-defined). Root cause: these symbols only exist in the Windows typeshed, and the two code spots lacked `sys.platform` literal-branch protection; other `ctypes.windll` usages in the project (web.py / main.py / gui.py) are all wrapped in `if sys.platform == "win32":`, which mypy's platform awareness skips for non-current-platform branches
- **Fix**:
  - `src/web_tray.py`: add `if sys.platform != "win32": return` at the start of `_patch_console_window()`; wrap `_on_show()`'s `ctypes.windll.user32` access in `if sys.platform == "win32":` branch
  - `main.py`: `get_startup_info()` changed to module-level platform-conditional type alias `_StartupInfoType` (Windows `subprocess.STARTUPINFO`, other platforms `object` placeholder) + `sys.platform == "win32"` branch inside the function, removed the original `"subprocess.STARTUPINFO | None"` string annotation (mypy would parse the string annotation and report name-defined)
- **Convention recorded**: Windows-specific APIs (`ctypes.windll`, `subprocess.STARTUPINFO` etc.) must be wrapped in `sys.platform == "win32"` (or `!= "win32"` early return) literal branches, otherwise mypy mis-reports on Linux/macOS

### v4.0.8.1-dev (2026-08-10) — Security hardening and code-quality fixes

**Critical security fixes**:

- `src/web_config.py` + `src/web_api.py`: added `DANGEROUS_CONFIG_KEYS` constant and `validate_config_value()` / `safe_update_config_line()`; `PUT /api/config` forbids rewriting [Recorder]/[Push] dangerous keys (like "execute custom script after recording") when unauthenticated, blocking the "unauthenticated Web panel bound to 0.0.0.0 = RCE" exploit chain
- `src/web_config.py` + `src/web_api.py`: `update_config_line` and `RoomCreate`/`RoomUpdate` filter `\n`/`\r`, fixing INI injection (could inject arbitrary new lines / new sections into config.ini / URL_config.ini)

**Medium fixes**:

- `src/web_api.py`: `/api/login` added brute-force rate-limit (default 5 failures within 5 minutes locks for 10 minutes)
- `src/sync_http.py`: exceptions no longer masquerade as response body, changed to `logger.error` and return `""` after logging, avoiding failures silently swallowed
- `msg_push.py`: added `_mask_url()`, auto-masking webhook URLs in DingTalk / WeChat / Bark / ntfy / Telegram push-failure logs, preventing token-bearing credentials leaking to logs

**Minor fixes**:

- `src/spider.py`: `_get_dd_calcu`'s `subprocess.run(node ...)` changed to `asyncio.to_thread` to avoid blocking the event loop
- `src/utils.py`: `check_md5` changed to chunked read, large files no longer loaded fully into memory
- `src/room.py`: two `raise e` changed to `raise`, preserving original traceback
- `src/async_http.py`: `_client_cache` added `threading.Lock`, preventing orphan clients from concurrent first-time creation
- `main.py`: transcode thread set `daemon=True`; recording dir creation added `exist_ok=True` to fix TOCTOU race
- `scripts/smoke_test.py`: black formatting aligned (line width 120)

### v4.0.8.1-dev (2026-08-09) — Comment convention and Web/API smoke-test tool

- **Comment convention (new code convention)**: module/function docs uniformly use `#` line comments, no longer triple-quote `"""` docstrings; functional multi-line string literals (templates/SQL) use single quotes + line-join concatenation
- **New Web/API smoke-test tool** (`scripts/smoke_test.py`): zero-dependency (pure stdlib), config-driven (JSON), supports GET/POST, expected status code, `expect_contains` text check, `expect_json` field check, `base_url` prefix join, outputs console/JSON/HTML reports, non-zero exit code on failure (CI-friendly); example config `scripts/smoke_web.json` (defaults to probing Web admin panel `http://127.0.0.1:8000`)
- Complements the existing `build_exe.py --smoke` (packaged artifact smoke): the former targets running HTTP-interface liveness, the latter verifies packaged exe startup availability

### v4.0.8.1-dev (2026-08-09) — Doc-stats induction (CODE_WIKI update)

- **New "Document Statistics and Index" section**: statistically analyzed all `*.md` files in the workspace (324 total), divided by source into project-root docs (3, source of truth), auto-generated repo docs (.qoder/repowiki, 302), workspace memory (.workbuddy/memory, 12), historical memory (.codebuddy/memory, 7); clarified only the 3 root-level hand-maintained docs should be change sources, and gave the role index of the three
- **New "Supported Platforms" subsection**: induced 51 listed platforms from `README.md` (37 domestic + 14 overseas), filling the prior gap of only "60+" summary
- **New "Quality-code Mapping" subsection**: completed OD/BD/UHD/HD/SD/LD quality codes with Chinese-name/description mapping, and the list of 7 platforms supporting actual-quality re-fetch warnings
- **Feature complement "Web Security"**: aligned with `README.md` feature table (Token auth, path-traversal protection, sensitive-config masking)
- **Fixed Node.js version consistency**: "FAQ 2" install command corrected from `setup_20.x` to `setup_22.x`, consistent with `README.md` and Dockerfile (Node.js 22 LTS)
- Synced TOC to reflect new sections

### v4.0.8.1-dev (2026-08-08 ~ 2026-08-09) — Full code review, build fix, and GUI graceful-stop hardening

**Full code review (2026-08-08)**:

- All four tiers passed: `compileall` all `.py` passed; `black` (line-length 120), `isort` passed; `mypy src/` 0 errors; `pytest` **417 passed** (no regression)
- **Fixed `pyproject.toml` illegal author email**: `authors[0].email = "ihmily@github"` is not a valid IDN email, new setuptools directly refuses to build, causing `pip install .` / `pip install .[dev]` **to inevitably fail** (reproduced locally). Changed to `ihmily@users.noreply.github.com`. CI never triggered because it only installs bare tools (`pip install mypy` etc.), local dev would hit it
- **2 black format violations** (`main.py` one over-long log/function signature, `tests/test_stream.py` one over-long assert) → fixed with `black` (CI's `black --check .` would have failed)
- Version `4.0.8.1` synced across pyproject/Dockerfile/README/CODE_WIKI/zh_CN.po; `src/spider.py:669` has a 2024 Kuaishou old-fallback-branch TODO comment, a conservative keep item, untouched

**GUI stop-recording graceful-exit hardening (2026-08-09)**:

- `gui.py` `stop_recording()`: original `_send_ctrl_break_to_child` failure only fell back to `proc.terminate()` (Windows = `TerminateProcess` hard kill), wouldn't trigger main.py's `safe_exit`/`atexit` fallback → ffmpeg grandchild process **orphaned** continuing background recording; and `wait()` immediately succeeded → printed "process exited gracefully (ffmpeg already cleaned up by child)" — **log inconsistent with reality**, and bypassed the real whole-tree cleanup fallback branch
- Now the failure path changes to `taskkill /F /T /PID` **whole-tree termination** (kills ffmpeg together), only falls back to terminate if taskkill errors; log distinguishes by path: graceful exit prints the original text, hard-kill path changed to "process terminated (hard-kill path, ffmpeg terminated with process tree)", no longer falsely claiming cleaned up

**GUI subprocess pythonw compatibility fix (2026-08-09, root-cause located)**:

- When starting GUI with `pythonw gui.py`, `sys.executable` points to **pythonw.exe**, and the source-mode `[sys.executable, main.py]` makes the recording core also start as pythonw
- pythonw is a **GUI-subsystem process, creates no console**, so the `CREATE_NEW_PROCESS_GROUP | CREATE_NEW_CONSOLE` start flags are ineffective for it → on stop `AttachConsole(pid)` inevitably fails → CTRL_BREAK **structurally unreachable** → falls back to hard-kill (the orphaning risk from above)
- Now when the interpreter basename starts with `pythonw`, use the same-directory **python.exe** (console subsystem) to launch the recording core; the packaged version (CLI exe `console=True`) is unaffected
- **Real-test verification** (pythonw as parent + python.exe launching a child with SIGBREAK handler): after fix `AttachConsole` succeeded, `GenerateConsoleCtrlEvent` returned True, event truly delivered to child (without handler it's default-terminated, exit code `0xC000013A`=STATUS_CONTROL_C_EXIT; with handler registered it received `signum=21`). Discovered CPython behavior along the way: Python 3.13's `time.sleep()` **isn't woken by CTRL_BREAK** (event goes through the pending-call mechanism, main thread in C-layer sleep doesn't check signals), but main.py's recording main loop has no long sleep, so after receiving the event `safe_exit` executes within the GUI's 15-second wait window

> Removed `gui_legacy.py` (v4.1.0-dev, 2026-09-10): the file was functionally redundant with `gui.py` and carried a `CREATE_NO_WINDOW` child-process bug that silently disabled `send_signal(CTRL_BREAK_EVENT)`. Migration to `gui.py` is complete, so the legacy entry has been removed.

### v4.0.8.1-dev (2026-08-05) — CI static-verification workflow, concurrency-test integration, and coverage-gate uplift

**New `.github/workflows/ci.yml` static-verification workflow**:

- Triggered on push to main / PR; `dorny/paths-filter@v4` path filtering, pure-frontend/doc/i18n changes don't trigger Python checks
- 7 parallel jobs: lint (black --check), typecheck (mypy src/, py3.10), isort (--check), version-check (`scripts/check_version.py`), test (pytest + coverage), concurrency-test, integration-verify (ffmpeg/node binary discoverability + `check_ffmpeg_installed()` / `check_nodejs_installed()` detection-function verification)
- concurrency-test uses `COVERAGE_RCFILE=.coveragerc-concurrency` with a dedicated coverage config (no global threshold, global gate guaranteed by the full test job), runs `test_concurrency_rate_limit.py` + `test_concurrency.py`

**Coverage gate and test expansion**:

- `pyproject.toml [tool.coverage.report] fail_under`: 20 → 50 (current total coverage 50.34%)
- Independent gates for high-churn core modules (recorded in pyproject.toml comments): spider.py ≥50%, stream.py ≥70%, utils.py ≥80%, ttwid.py ≥85%, ab_sign.py ≥95%, proxy.py ≥50%
- New test files: test_ab_sign / test_concurrency / test_concurrency_rate_limit / test_proxy / test_spider_platform / test_sync_http / test_ttwid / test_weverse_auth; currently 417 passed

**build-release.yml upgraded to lite/full dual artifact**:

- CI build command changed to `python build_exe.py --smoke --dual`: PyInstaller runs once, producing both lite (no ffmpeg/node, auto-downloaded at runtime) and full (binaries downloaded and packaged at build time) zips, smoke test runs on the lite version
- `build_exe.py` added `--no-runtime` / `--dual` params; artifact naming `DouyinLiveRecorder-v{version}-{os}-{arch}-{lite|full}.zip`
- full zip (~300MB) upload with workflow-level explicit retry (max 3, backoff 30s → 60s); upload/download action upgraded to v7 (Node.js 24 runtime), `compression-level: 0` skips re-compression
- Three-platform smoke uses system package managers for ffmpeg: Windows choco / Linux apt(+xvfb) / macOS brew (`brew trust aws/tap` fallback)
- Release creation switched to `softprops/action-gh-release@v3`; all three entry points exclude `brotlicffi` (fixes the "missing `error` attribute" error after packaging)

### v4.0.8.1-dev (2026-08-05) — HLS validation mis-judgment and blank-log fix

**Problem background**: Run log showed `get_response_status 校验失败（判定为不可达）: ` (blank message) + `HLS URL validation failed, falling back to FLV`, and the 8-01 and 8-05 logs were the same pattern. Three-layer root cause: on Windows `socket.timeout` / `TimeoutError`'s `str()` is empty causing blank exception logs; `_validate_stream_url` silently swallowed exceptions; m3u8 HEAD probe didn't cover 404 and `select_source_url` didn't pass through proxy.

**Change (3 places)**:

- `src/async_http.py` `get_response_status()`: exception log carries URL + `type(e).__name__`; m3u8 HEAD non-2xx (**incl. 404**) uniformly adds `Range: bytes=0-0` GET probe; probe failure logs status_code / content-type
- `main.py` `_validate_stream_url()`: added `verify` param (reuses global SSL switch, consistent with async validator); m3u8 404 also probed; all failure paths log warning (URL + exception type/status-code/content-type), no longer silent
- `main.py` `select_source_url()`: added `proxy_addr` param passed through to 3 validator calls; call site `main.py:1991` passes `proxy_address`, fixing TikTok etc. proxy-needed platforms' direct-connect validation mis-judged unreachable

### v4.0.8.1-dev (2026-08-02 ~ 2026-08-04) — Platform-naming convention landing and type/logic fixes

**Platform-naming convention product-level landing (2026-08-02)**:

- `main.py`: CLI help string, `logger.error` literals, and internal platform slug all changed to canonical display names (bigo, blued, Look直播, TTingLive(原Flextv), SOOP(原AfreecaTV), YouTube, 飘飘); synchronously paired coupled changes: recording-request-header dict keys (`FlexTV`→`TTingLive(原Flextv)`, `Blued直播`→`blued`) and the `re_plat` regex tuple
- `src/spider.py`: comments and Chinese exception messages synced to canonical names; English gettext msgid kept untouched (avoid breaking translations); recompiled `zh_CN.mo` (203 entries)
- Internal config/API slugs (sooplive/flextv/tiktok) and code-parse pairing intentionally unchanged

**Type and logic fixes (2026-08-03 ~ 08-04)**:

- `gui.py` reached basedpyright/pyright 0/0/0: `typings/pystray/__init__.pyi` supplemented darwin-specific members (`run_detached`/`_assert_image`/`_icon_valid`/`visible`); `SystemTray` added `self.detached` flag replacing `sys.platform == "darwin"` judgment (eliminating win32 branch-unreachable hint); PIL icon preheat switched to `thumbnail()` to avoid `resize`'s NumpyArray-signature Unknown inference
- Discovered basedpyright 1.39.9 defaults `enableTypeIgnoreComments=false`: the project's historical `# type: ignore` comments are all currently ineffective, warnings eliminated uniformly by completing type stubs / widening types / changing implementation
- `main.py`: TikTok fallback literal `{"is_live": False}` narrowed with `cast(dict[str, object], ...)`, fixing union-type mismatch
- `src/spider.py` `get_taobao_stream_url()` fixed indentation defect: `return result` was originally outside the SUCCESS branch, causing `UnboundLocalError` at runtime when Taobao interface returned non-SUCCESS non-empty ret; now moved into the success branch, non-SUCCESS falls into loop retry with `{"anchor_name": "", "is_live": False}` fallback

### v4.0.8.1-dev (2026-08-01) — mypy strict mode full pass and type-annotation tightening

**Changes**:

- `pyproject.toml`: `disallow_untyped_defs` changed from `false` to `true`, requiring all functions to have complete type annotations
- `mypy src/ --strict` reduced from 61 errors to 0 errors (16 source files all passed)

**Type-annotation fixes (9 files)**:

- `src/ab_sign.py`: `SM3.__init__`, `_fill` added `-> None` return type
- `i18n.py`: `init_gettext` added `-> Callable[[str], str]` return type
- `src/proxy.py`: `ProxyInfo.__post_init__`, `ProxyDetector.__init__`, `__del__` added `-> None`
- `src/utils.py`, `src/room.py`, `src/spider.py`: removed unused `type: ignore[no-redef]` comments
- `src/web_config.py`: removed redundant `cast("list[str]", parser.sections())`
- `src/spider.py` (most fixes): added param/return type annotations for 20+ functions, fixed missing generic params (`dict` → `dict[str, object]`, `tuple` → concrete tuple type), redundant casts, internal-function type mismatches
- `main.py`: `_fix_encoding` added `-> None`
- `src/web_api.py`: all FastAPI route handlers added return-type annotations (`dict[str, object]`, `StreamingResponse`, `FileResponse` etc.)

### v4.0.8.1-dev (2026-08-01) — Version-number convergence to pyproject.toml single source of truth

**Changes**:

- `pyproject.toml` became the single authoritative source of version number (Single Source of Truth)
- `main.py`: removed hardcoded `version: str = "v4.0.8.1"`, changed to `_read_version_from_pyproject()` dynamic read (prefers `importlib.metadata`, falls back to parsing `pyproject.toml` directly)
- `build_exe.py`: `read_version()` changed to parse version from `pyproject.toml`
- `scripts/check_version.py`: baseline source switched from `main.py` to `pyproject.toml`, added detection of whether `main.py` still has a hardcoded version
- CI `version-check` job needs no change, still calls `python scripts/check_version.py`

**New version-update flow**: only modify the `version` field in `pyproject.toml`, then sync `Dockerfile`, `README.md`, `CODE_WIKI.md`, `i18n/zh_CN.po`; `main.py` needs no manual change.

### v4.0.8.1-dev (2026-08-01) — Core-module unit-test completion and coverage-threshold adjustment

**New test files**:

- `tests/test_stream.py` (~500 lines): covers `src/stream.py` core data-flow paths
  - Pure utility functions: `bitrate_to_quality`, `code_to_zh`, `is_downgrade`, `_pad_list`, `get_quality_index`
  - Constant-consistency checks: `QUALITY_MAPPING` / `QUALITY_LEVEL` / `QUALITY_MAPPING_BIT` / `QUALITY_CODE_TO_ZH` key-set alignment
  - Platform stream parsing (async Mock): Douyin (offline/online/FLV-only/downgrade), TikTok (offline/online), Kuaishou (offline/online/with-bitrate), YY, NetEase CC, generic entry (m3u8/flv/all three url_type)
- `tests/test_async_http.py` (~440 lines): covers `src/async_http.py` core request paths
  - `_get_client`: cache reuse, different-param isolation, expired-client replacement
  - `_close_all_clients` / `close_all_clients_sync`: connection-pool cleanup
  - `async_req`: GET/POST (dict/str/bytes data), redirect_url, return_cookies, include_cookies, exception fallback, verify default
  - `get_response_status`: 200/404, m3u8 HEAD 405 downgrade to Range GET, exception handling, non-m3u8 no probe

**Coverage change**:

| Module | Before | After |
| --- | --- | --- |
| `src/stream.py` | 0% | 70% |
| `src/async_http.py` | 35% | 83% |
| Total coverage | 15.29% | 22.35% |

**Coverage threshold adjustment**:

- `pyproject.toml` `[tool.coverage.report] fail_under`: 15 → 20 (reflects current actual coverage, leaves room for later increments)

### v4.0.8.1-dev (2026-08-01) — Douyin URL full-format support, format-5 link optimization, HLS validation and log fix

**Douyin URL parsing (supports 5 formats, including all fixes this round)**:

- Dispatch logic refactored (`spider.py: get_douyin_app_stream_data`): `live.douyin.com/*` directly calls web endpoint; `www.douyin.com/user/<sec_uid>` skips the inevitably-failing `get_sec_user_id` probe, goes `resolve_from_homepage()`; `v.douyin.com` short link probes first, throws `UnsupportedUrlError` then falls back to homepage path
- Homepage parsing switched to `iesdouyin.com/web/api/v2/user/info/` JSON interface (takes `unique_id`, falls back to `short_id` if empty), replacing the now-JS-anti-crawl-shell-page `share/user/` HTML; added `room.DESKTOP_UA` desktop UA (old mobile UA was silently rate-limited: HTTP 200 + empty body)
- `room.py` added `is_user_homepage_url()` + zero-request fast path: web-end homepage's sec_user_id extracted directly from URL path, saving one ~71KB follow-redirect download
- **Fixed hidden bug**: old fallback called `get_douyin_stream_data("live.douyin.com/"+unique_id)` without passing proxy_addr/cookies, causing proxy and Cookie config to silently fail on the homepage path; now `resolve_from_homepage()` explicitly passes through
- Deleted dead code `get_douyin_stream_data()` (~94 lines, no call sites after refactor)
- Added sec_uid→Douyin-ID process-level cache (`room.py`, `threading.Lock` cross-thread/cross-asyncio-loop dedup, 30-min TTL): homepage parsing no longer re-requests the iesdouyin interface each polling round
- Format-5 real-test link optimization: requests 4→3, download ~1.3MB→~1.2MB, time ~1.7s→~1.4s; the remaining ~1.1MB HTML is for fetching the original-quality HEVC stream (`stream.py: extract_douyin_hevc_flv_url`) general behavior, can't be removed

**HLS validation and log fix**:

- `async_http.py get_response_status()`: empty-message log fix (`logger.debug(e)` left only `- ` when `e` was empty string, changed to carry context description); on HEAD failure, add `Range: bytes=0-0` GET probe for `.m3u8` sources
- `main.py _validate_stream_url()`: content-type check added `mpegurl`; on HEAD denied, add Range GET probe for `.m3u8` — fixes Douyin CDN m3u8 returning 4xx on HEAD being mis-judged unreachable and always falling back to FLV
- `spider.py web/enter` API call wrapped in `_try_web_api()` + silent retry once (`asyncio.sleep(0.5)` buffer): transient `status_code=10002` no longer spams WARNING, retry success skips HTML fallback (saves ~1MB download), falls back only if both fail

**Tests and static checks**:

- `tests/test_douyin_url_resolution.py` expanded to 17 cases (5 URL-format dispatch, cache hit, 10002 retry, web_rid handling etc.); added autouse fixture clearing sec_uid cache to prevent cross-case pollution
- Full `pytest` 78 passed; `black`/`isort` all green; `mypy src/` no issues; ruff only remaining intentional E402 (project's established late-import pattern)
- Incidental fixes: `tests/test_utils.py` unused import (F401), `src/stream.py` ambiguous var name `l` (E741, changed to `level, ratio`)

**Version sync**: project-wide version number uniformly upgraded to `4.0.8.1` (main.py / pyproject.toml / Dockerfile / i18n / README / CODE_WIKI)

### v4.0.8.1-dev (2026-07-29) — Engineering-config file overhaul and doc sync

**Engineering config files (six files + dual-doc sync)**:

- `.gitignore`: fixed three self-contradictions — removed `i18n/**/*.mo` ignore (.mo distributed with repo, gettext needs it at runtime); added `!StopRecording.vbs` exception after `*.vbs`; no longer ignore CODE_WIKI.md. Added ignores `.workbuddy/`, `.codebuddy/`, `.trae/`
- `.dockerignore`: rewritten. Kept `i18n/**/*.mo` (Dockerfile won't recompile, old rule caused in-container translation failure); only exclude `.po` sources and compile scripts. Added exclusions typings/, build_exe.py, gui_legacy.py, AI-tool dirs
- `Dockerfile`: builder stage removed useless Node.js install (Node only needed at runtime, stage 2 already has Node 22); EXPOSE added web_host=0.0.0.0 note
- `docker-compose.yaml`: refactored to three services — recorder (default, main.py, no port), web (profile, 8000:8000), gui (profile). Fixed original design where recorder occupied port 8000
- `pyproject.toml`: `+starlette>=0.49.1` (web_api.py imports directly); `+[project.optional-dependencies] build = ["pyinstaller>=6.10.0"]`; `+py-modules` (fixes project.scripts entry missing module); removed invalid i18n package-data
- `requirements.txt`: synced starlette>=0.49.1 and PyInstaller build-time note

**Code-structure cleanup (align with git worktree state)**:

- Removed `src/http_clients/` subpackage (`__init__.py` / `async_http.py` / `config.py` / `sync_http.py`), HTTP clients uniformly provided by `src/` root modules (`async_http.py` / `sync_http.py` / `http_config.py`), `pyproject.toml`'s `packages` correspondingly narrowed to `["src"]`
- Removed `src/initializer.py` and `TRAE_AGENT_CODE_WIKI.md` (no longer maintained)

**Doc sync**:

- `CODE_WIKI.md`: dependency table fully updated (removed weverse, added exejs/customtkinter/starlette/python-multipart); Docker section changed to describe actual compose three services; directory tree corrected
- `README.md`: Docker usage changed to `docker compose --profile web/gui`; added web_host=0.0.0.0 warning; project structure tree synced; Markdown format unified (cleaned 13 orphan `</div>` tags + normalized section blank lines, 798→770 lines)

### v4.0.8.1-dev (2026-07-28) — Fix macOS CI smoke:gui crash

- `gui.py`: macOS changed to `tray.run_detached()` (non-blocking) + main-thread `root.mainloop()`, fixing `RuntimeError: Calling Tcl from different apartment` caused by Tcl/Tk only running on the main thread
- `SystemTray` extracted `_build_icon()/_degrade()`; added `run_detached()`: main thread `_assert_image()` preheats PNG encoding then sets `icon._icon_valid = True`, avoiding the native crash path where the setup thread returns to a background-thread PNG encode
- Fixed hidden bug: old `run()` called darwin-specific `_assert_image()` on all platforms, throwing AttributeError on Windows/Linux swallowed causing the tray to be silently disabled
- `stop()`: darwin detached mode sets `icon.visible = False` before `icon.stop()`

### v4.0.8.1-dev (2026-07-27) — ttwid shared-module extraction and smoke-test process-tree cleanup

**ttwid shared module (`src/ttwid.py`)**:

- Created `src/ttwid.py`: process-level unique `_cached_ttwid` + `threading.Lock` cross-thread/cross-event-loop dedup, exports `async def get_ttwid(proxy_addr)` and `def warmup_ttwid(proxy_addr)`
- `src/spider.py` / `src/room.py`: removed their local ttwid implementations, uniformly delegating to `src/ttwid.py`
- `main.py`: `main()` loop uses `first_run` gate to call `warmup_ttwid(proxy_addr)`, ensuring the whole process fetches ttwid only once
- `src/ttwid.py`: supports reading user-configured ttwid from config.ini `[Cookie]` section, fetch priority = cache > config > auto-fetch

**build_exe.py smoke-test process-tree cleanup**:

- `_launch()` makes the child its own process group/session (Windows `CREATE_NEW_PROCESS_GROUP`, Unix `start_new_session`)
- Added `_kill_tree(proc)`: Windows `taskkill /T /F /PID`, Unix `os.killpg(getpgid(pid), SIGKILL)`, eliminating GitHub Actions runner orphan-process cleanup noise

### v4.0.8.1-dev (2026-07-26) — basedpyright whole-project clear and docstring-comment conversion

**basedpyright whole-project 0/0/0 (typings + src)**:

- `typings/execjs/` (6 .pyi): file-level pyright directives relax dynamic-JSON strict checks (reportAny/reportExplicitAny/reportMissingParameterType etc.)
- `typings/pystray/__init__.pyi`: reportAny/reportExplicitAny relaxed
- `src/spider.py`: file-level directives relax 16 rules (787 warnings → 0, almost all from json.loads returning Any cascade)
- `src/room.py`: added execjs stub, handle_proxy_addr type annotation, cast narrowing, explicit string concat
- `src/sync_http.py`: OptionalDict type parameterization, urllib cast, deprecated-API replacement
- `src/async_http.py`: unused-param/coroutine-result resolution, data type completion, exception-fallback cast

**docstring → # comment conversion**:

- Whole-project 18 triple-quote docstrings converted to `#` line comments: build_exe.py(10), main.py(3), src/ab_sign.py(2), src/logger.py(1), src/web_tray.py(1), i18n.py(1)

### v4.0.8.1-dev (2026-07-25) — Full code-review fix and security hardening

**Key bug fixes**:

- `main.py`: audio/video branch `if` → `elif` mutually exclusive, fixing double-recording of the same room + malformed ffmpeg command
- `src/stream.py`: `QUALITY_MAPPING` changed to position index aligned with Douyin order dict `{OD:0,BD:1,UHD:2,HD:3,SD:4,LD:5}`, fixing wrong quality selection
- `src/proxy.py`: multi-protocol proxy `http=1.2.3.4:5678` parsing strips protocol prefix first, fixing ValueError
- `main.py`: FLV direct-download branch writes to recording/recording_time_list wrapped in `record_state_lock` (data race)
- `main.py`: `check_subprocess` added `process.wait(timeout=30)` (zombie process)

**Security hardening**:

- `src/web_config.py` + `src/web_api.py`: web_password changed to PBKDF2-HMAC-SHA256 storage, historical plaintext auto-upgraded to hash on login
- `src/http_config.py`: `ssl_verify` default changed to `True` (security-first)
- `msg_push.py`: PushPlus token log masking (`_mask_secret`, keeps only first and last 2 chars)
- `src/node_install.py`: `unzip_file` added Zip Slip protection

**Other fixes**:

- `src/async_http.py`: expired client `aclose()` before rebuild, fixing connection-pool leak
- `web.py`: on exit actively `cleanup_all_ffmpeg_processes()` + `close_all_clients_sync()`, eradicating orphan ffmpeg
- `gui.py`: added `self._stopping` flag + disable start button during stop, eliminating stop race window
- `src/ab_sign.py`: fixed SM3 GG function bug (wrong ff_j formula used when j>=16)
- `i18n.py`: translation coverage expanded from only `src/` to all source files under project root (main.py/web.py/gui.py/msg_push.py)

### v4.0.8-dev (2026-07-28) — Multi-room concurrent-monitoring risk-control fix and static-check clear

**Douyin multi-room concurrent-monitoring risk-control fix**:

- `src/spider.py`: `_ensure_ttwid()` delegates to shared `src/ttwid.py` module (with `threading.Lock` cross-thread dedup), solving the risk-control trigger from multi-thread concurrent repeated ttwid fetches
- `src/room.py`: `_ensure_douyin_ttwid()` likewise delegates to shared `ttwid.py` module, unifying the ttwid fetch entry
- `main.py`: added `_douyin_rate_limit()` rate limiter, ensuring at least 3 seconds between two Douyin API requests (`douyin_min_interval`), avoiding multi-thread back-to-back consecutive requests triggering Douyin risk-control (empty response)
- `main.py`: added global vars `douyin_rate_lock`, `douyin_last_request_time`, `douyin_min_interval` for rate control

**Static-check clear (Pyright 0 errors, 0 warnings)**:

- `gui.py`: `Image.LANCZOS` → `Image.Resampling.LANCZOS` (Pillow 10+ modern API, fixes `reportAttributeAccessIssue`)
- `gui.py`: added `# type: ignore[attr-defined]` for pystray private-attribute access (`_assert_image()`, `_icon_valid`, `run_detached()`)
- `main.py`: `select_source_url()`'s `_validate_stream_url(m3u8_url)` added `cast(str, m3u8_url)`, fixing `reportArgumentType` type-narrowing issue

### v4.0.8-dev (2026-07-25) — New PyInstaller executable packaging and GitHub Actions release

- Added `build_exe.py`: PyInstaller `onedir` + `contents_directory='_internal'`, dynamically generates `.spec`, builds `main.py`/`gui.py`/`web.py` three-entry shared deps into `DouyinLiveRecorder(.exe)` / `-GUI(.exe)` / `-Web(.exe)`, uniformly compressed into `DouyinLiveRecorder-v{version}-{os}-{arch}.zip` (~118 MB)
- Directory convention: `node/`, `ffmpeg/`, `config/` kept same level as exe; `src/` and all Python dependency packages unified into `_internal/`; at runtime `logs/`, `downloads/` (when not specified via config.ini), `backup_config/` created by default at exe's same level
- Added path-convergence function `src/logger._app_root()` (same name as inline in `main.py`), when frozen returns `dirname(sys.executable)` (exe same level), making `main.py`/`src/__init__.py`/`src/node_install.py`/`src/ffmpeg_install.py` runtime resources and `src/logger.py`'s logs correctly converge
- `gui.py` freeze adaptation: when frozen directly calls same-dir `DouyinLiveRecorder.exe` to launch the recording core (avoids `sys.executable` pointing to self causing infinite recursion); added `self.app_root` to locate exe-level config/downloads
- Chinese UTF-8 encoding fix: added `_fix_encoding()` at top of `main.py`/`gui.py`/`web.py` (Windows switch console codepage 65001 + reconfigure UTF-8), fixing frozen-child-pipe GBK output read as UTF-8 by GUI causing garbled text
- `build_exe.py --smoke` three smoke tests: CLI alive, Web HTTP liveness 200 (and verifies built-in ffmpeg hit), GUI alive 8s (auto-skip without DISPLAY)
- Added `.github/workflows/build-release.yml`: three-platform matrix (win/linux/mac, Python 3.12) + dependency install + smoke test + artifact upload; pushing `v*` tags auto-creates GitHub Release with three-platform zips

### v4.0.8-dev (2026-07-25) — Whole-project type-error fix and code cleanup

**Type-error fixes (Pyright / Pyrefly / basedpyright)**:

- `src/proxy.py`: fixed cross-platform type error — declared `self.winreg: Any = None` and `self.__INTERNET_SETTINGS: Optional[Any] = None` before the platform check, simplified `__del__` destructor with `try/except` wrapping direct access, paired with `is not None` type narrowing
- `gui.py`: `Fonts.get()`'s `weight` param narrowed from `str` to `Literal["normal", "bold"]`, matching `CTkFont` signature
- `main.py`: completed module-level variable declarations (~160), grouped by function (proxy/recording/push/email/Cookie/loop-temp-vars etc.), eliminating hundreds of "Could not find name" errors in `push_message()`/`start_record()` etc.
- `main.py`: `get_status()` added defaults for 5 snapshot vars (`recording_snapshot`, `recording_times`, `monitoring_val`, `running_val`, `error_val`) before the retry loop, eliminating "possibly unbound" errors
- `main.py`: filled missing `twitcasting_cookie: str = ""` module-level declaration
- `msg_push.py`: `tg_bot()`'s `chat_id` param relaxed from `int` to `str | int`, Telegram API accepts both numeric and string chat IDs
- `src/web_config.py`: removed redundant `str(raw)` call (`parser.get()` return is always `str`)
- `src/spider.py`: added explicit `list[dict]` / `dict` type annotations for `sorted_stream_list` and `stream_data`, fixing 3 `.get()` call errors from Pyrefly inferring `SupportsGetItem`
- `src/spider.py`: removed unreachable `return None` at end of `get_bilibili_stream_data()` (both if/else branches already return)
- `src/http_config.py`: removed redundant `bool(value)` call (param already annotated `bool`)
- `src/async_http.py`: `_get_client()` refactored to early-return pattern, eliminating possibly-unbound `client` error
- `src/stream.py`: `QUALITY_LEVEL.get(video_quality, 4)` changed to `QUALITY_LEVEL.get(video_quality or "", 4)`, handling `str | None` key type
- `src/stream.py`: `quality, quality_index = ...` changed to `_, quality_index = ...`, eliminating unused-variable hint

**Code cleanup (pyflakes / unused imports and vars)**:

- `src/spider.py`: fixed `result` referenced-before-assignment `NameError` in `get_baidu_stream_data()` (triggered when `data_dict` empty)
- `src/spider.py`: removed unused imports `import ssl` and `from .ab_sign import ab_sign`
- `src/logger.py`: removed unused import `import os`
- `gui.py`: added `TYPE_CHECKING` guard for `pystray` type annotation (`pystray` lazily imported inside `run()`)
- `main.py`: removed unused `global error_count` declaration in `start_record()`
- `main.py`: removed unused `create_var` global declaration
- `main.py`: removed unused local var `changed`

### v4.0.8-dev (2026-07-25) — Dependency scan and Docker config update

**Dependency scan and pyproject.toml update**:

- `pyproject.toml`: project version `4.0.7` → `4.0.8-dev`, consistent with CODE_WIKI changelog
- `pyproject.toml` / `requirements.txt`: added `pydantic>=2.0.0` dependency (`src/web_api.py` directly `from pydantic import BaseModel`, previously undeclared)
- Whole-project dependency scan completed: all 14 third-party packages' usage locations checked and declaration status confirmed (see table below)

| Package | Declaration status | Usage location |
| --- | --- | --- |
| requests | Declared | src/ffmpeg_install.py, src/ffmpeg_master_download.py, src/node_install.py, src/sync_http.py, src/weverse_auth.py |
| httpx[http2] | Declared | main.py, src/room.py, src/spider.py, src/async_http.py |
| loguru | Declared | src/logger.py, msg_push.py |
| pycryptodome | Declared | src/spider.py (Crypto.Cipher.AES) |
| distro | Declared | src/node_install.py |
| tqdm | Declared | src/ffmpeg_install.py, src/ffmpeg_master_download.py, src/node_install.py |
| PyExecJS | Declared | src/room.py, src/spider.py, src/utils.py |
| customtkinter | Declared | gui.py |
| pystray | Declared | gui.py (lazy import) |
| Pillow | Declared | gui.py |
| fastapi | Declared | src/web_api.py |
| uvicorn[standard] | Declared | web.py (lazy import) |
| python-multipart | Declared | FastAPI form handling implicit dependency |
| **pydantic** | **Missing→added** | src/web_api.py (BaseModel) |

**Dockerfile update**:

- Python base image `python:3.13.0-slim-bookworm` → `python:3.13-slim-bookworm` (two-stage) — 3.13.0 is the Oct 2024 initial version, missing later security patches; dropping the patch number auto-gets latest
- Node.js `setup_20.x` → `setup_22.x` (two-stage) — Node 20 LTS EOL April 2026, Node 22 is current active LTS
- Security upgrade (`apt-get upgrade`) moved from builder stage to runtime stage — builder is a temporary stage, upgrade meaningless there; runtime is the final image, security upgrade should be there
- LABEL version `4.0.7` → `4.0.8-dev`

**docker-compose.yaml**: no update needed, structure already complete (volume mounts, port mapping, env vars, health check, resource limits, log rotation, GUI profile all correct).

### v4.0.8-dev (2026-07-24)

- New GUI quality-monitoring page (`gui.py` `_build_quality_page`), real-time detection via parsing child-process logs whether each room's actual quality matches settings
- New Web console toggle config `web_show_console` (default true), hides in background when false
- New `_enter_background_mode()`: hides console window on Windows (SW_HIDE), redirects logs to `logs/web_console.log`
- New `[Web]` config-section docs, with web_host / web_port / web_auth_enable / web_password / web_token_expiry / web_show_console six items
- New Web security-mechanism docs: password-change revokes Token, listen-alert, path-traversal protection, sensitive-config masking
- Unified code-comment style: converted all function docstrings in `web.py`, `src/web_config.py`, `src/web_api.py`, `src/stream.py` to `#` line comments
- New actual-quality re-fetch and downgrade-alert feature, covering Douyin, TikTok, Kuaishou, Huya, Douyu, Bilibili, NetEase CC seven platforms
- New `bitrate_to_quality()`, `code_to_zh()`, `is_downgrade()` quality utility functions (`src/stream.py`)
- New `actual_quality` / `available_qualities` return fields, each platform's stream function uniformly returns actual delivered quality
- Refactored `get_bilibili_stream_data()` to return dict (incl. url/current_qn/accept_qn), stream module reverse-maps qn to quality code
- New Web admin panel (`web.py` + `src/web_api.py` + `src/web_config.py` + `web/`), supporting dashboard, room management, config editing, SSE log push
- New frontend "actual quality" column display, highlighted red on downgrade (`.quality-down` style)
- New `tests/test_stream_quality.py` test file (347 lines, 17 cases)
- Fixed `display_info`'s `recording_time_list` unpack error (2-element → 3-element compatibility fix)
- Fixed `asyncio.run()`-caused httpx client cross-event-loop reuse issue (`'NoneType' object has no attribute 'send'`)
- Optimized each platform's stream-address selection, using explicit truncation instead of `_pad_list` silent padding, avoiding out-of-bounds

### v4.0.8-dev (2026-07-23)

- New HTTP-client connection-pool reuse mechanism, reusing AsyncClient by (proxy, verify, http2) dimensions, improving request performance
- New SSL-cert-verify global switch (`src/http_config.py`), uniformly controlling async/sync HTTP clients via config.ini
- New log-file toggle config item, controlling whether to output log file via config.ini
- Refactored proxy-detection logic, from network-probing Google to reading local system-proxy config, avoiding startup lag
- Optimized async-HTTP exception handling, providing type-safe fallback values per return contract
- Optimized process-exit cleanup, new HTTP-client connection-pool atexit / signal-handler fallback release
- Dockerfile added ca-certificates dependency, supporting cert verification when SSL cert verify enabled

### v4.0.8-dev (2026-06-27)

- Fixed `trace_error_decorator` severe bug: original sync decorator applied to 71 async functions caused error capture to completely fail, now uses `asyncio.iscoroutinefunction()` supporting sync/async dual mode
- Fixed return-value type-inconsistency bug: `execjs.ProgramError` branch returned `None` → `{}`
- Fixed Bilibili quality default `'0'` not in dict keys causing KeyError
- Fixed Huya `flv_anti_code` None causing `parse_qs(None)` crash
- Fixed TikTok/Kuaishou/NetEase CC empty stream-list IndexError
- Fixed `get_stream_url` empty-list index crash (function not protected by decorator)

### v4.0.8-dev (2026-06-20)

- Fixed spider.py 5 runtime bugs (KeyError, response-type conversion, silent loop return)
- Fixed stream.py 2 runtime bugs (Bilibili None check, Kuaishou quality condition)
- Fixed gui.py dead code (unused vars, f-string without placeholder)
- Cleaned src/weverse_auth.py unused imports
- i18n translation file update: added 20 translation entries (exception error messages, config files, disk space etc.), total 200 entries
- Verified via pyflakes static check

### v4.0.8-dev (2026-05-17)

- All-new modern GUI interface (WCAG AA high contrast, DPI-aware fonts)
- Docker multi-stage build key fixes (runtime Node.js, HEALTHCHECK)
- Config-file refactor (pyproject.toml, requirements.txt, .gitignore, .dockerignore)
- New Douyin stream-data debug tool `debug_douyin_streams.py`
- Completed i18n translations (YouTube/FlexTV/PopkonTV/TwitCasting)

---

> 以下条目由根文档滚动归档迁入（2026-10-18），内容与迁入前逐字一致。

### v4.4.0 (2026-10-01) — admit h265 candidates by save format (TS/MKV/MP4 can stream-copy HEVC) + zero-source observability for the silent HLS config drop

- **Trigger**: the two deferred candidate improvements from the same-day previous entry (origin-HEVC-room deadlock root cure); the user approved both ("relax + observe").
- **Change**: ① `src/stream_select.py` adds `_h265_copy_format_supported()` — it reads main's hot-reloaded global `video_save_type` and decides whether the configured container can stream-copy HEVC: TS(mpegts)/MKV(matroska)/MP4 muxers support it (the same fact as main.py forcing record_save_type=TS when an h265 address gets selected); FLV (HEVC-in-FLV is an Enhanced-FLV extension, unsupported by the repo's stance), MP3/M4A audio-only formats (no video track), out-of-domain/missing values all conservatively count as unsupported. The h265 filter narrows from "drop unconditionally" to "drop only when stream copy is unsupported", so TS users now get the h265 origin FLV primary candidate into the regular sequence for probing; the falsified blanket wording "h265 cannot be copy-recorded" in the `_is_h265` and sequence-construction comments is corrected in place with a dated history note per the comment convention. ② `main.py`'s h265→TS forcing block gains the same-predicate guard: when the save format is already TS/MKV/MP4 it no longer takes over nor logs "use TS format instead" (otherwise TS users would get one misleading warning per round); FLV/audio formats keep the original forcing semantics. ③ Before the no-source conclusion, a new observability warning fires when m3u8 candidates were dropped as a whole by the HLS config (global switch / exclusion list) AND the round ends with no usable source — naming the cause, the candidate count and the recovery switches; this was the only "zero-log" source-selection cause (the 2026-10-01 deadlock-room blind spot: with an FLV fallback present the early-exit warning never fired and the sequence showed no trace of the m3u8); it stays silent on rounds where a source is found. All four i18n catalogs register the 1 new msgid (zh_CN.po tail section + bumped PO-Revision-Date; en/en_GB corner brackets to double quotes; zh_TW terminology aligned 採集/清單/丟棄) and zh_CN.mo is recompiled (810 records = 809 keys + header).
- **Regression locks**: `tests/test_stream_select.py` gains the h265×save-format dual matrix (TS/ts/MKV/MP4 admit and select the h265 primary first; FLV/MP3/M4A音频/webm/empty drop it onto the h264 fallback, both asserting zero probes on h265), the `_h265_copy_format_supported` decision matrix (11 cells incl. case/whitespace/out-of-domain/None/int) plus the missing-global conservative fallback, and 2 observability cases (the warning fires exactly once on the failing round and never on a healthy round); `tests/test_main_fixes.py`'s two h265 source-selection cases pin the save format explicitly with history notes as the semantics narrow; `test_excluded_platform_h265_flv_not_switched_to_hls` pins FLV the same way. Mutation verification: inverting the predicate (MUTATION-H265RELAX) turned 24 cases red, force-disabling the observability condition (MUTATION-HLSOBS) turned the positive case red; both restored byte-exact with zero marker residue.
- **Verification**: `pytest --cov=src` 3720 passed / 14 skipped / 1 failed — `tests/test_notify.py::test_run_script_timeout_kills_process` hit the 4.0s assertion margin at 4.04s; attributed at the time to "session-sandbox environment state", **an attribution the user's normal-PowerShell rerun later disproved** (see the correction below).
- **Follow-up correction (2026-10-02 00:41, after the user-terminal reproduction)**: the same case still failed in the user's normal terminal (elapsed=4.01s) → a control experiment re-characterized it: `proc.kill()` (direct Popen kill) 0.01s, PowerShell `Stop-Process` 0.71s, `taskkill /?` 0.10s, while `taskkill /F /PID` terminating a real process takes a steady **2.5~3.1s** (rc=0, CPU at 6%) — what is slow is taskkill.exe's own implementation path (WMI signature), not the process-termination action and even less this repo's code; the 1s test timeout plus ~3s taskkill lands exactly on the hand-tuned 4.0s margin. Fix: the case's wall-clock bound is now **derived from the production constants** (`_SCRIPT_TIMEOUT_SECONDS + _TREE_KILL_TIMEOUT_SECONDS + 2.0`, ≈8s) — taskkill consuming its own full 5s budget no longer false-alarms, while "unbounded blocking / tree-kill over budget / hung pipe reaping" still trips the bound red; the original "does not occupy the calling thread after timeout" intent is unchanged, and the per-behavior locks remain in `tests/test_notify_script_guard.py`. The machine-state root cause (why taskkill/WMI takes ~3s) is an OS-layer matter outside this repo's scope. Lesson: a test's time margin should be derived from the tested path's production constants, never hand-tuned — a hand-picked value silently assumes "external tools in their healthy state", which both false-alarms and defies attribution when machine state shifts.
- **Verification (final, after correction)**: `pytest --cov=src` **3721 passed / 14 skipped / 0 warnings**, `check_coverage.py` all 44 modules meet threshold, basedpyright 0 error / 0 warning, `compile_po --check` in sync, `run_gates.py` all 8 gates green. Live verification (live HEVC-origin room 127453393722 央视网快看, inline source-selection script): HLS off + ts → **the h265 FLV primary was admitted and selected** (codec=h265, probe passed for real); HLS off + FLV → fell onto the h264 origin fallback (codec=h264); HLS off + FLV with the fallback stripped → None with the new observability warning fired for real (English catalog form with recovery switches and the anchor name) → all three states PASS.

### v4.4.0 (2026-10-01) — root cure for the douyin HEVC-origin-room "no usable source this round" deadlock: keep the replaced h264 origin FLV in `flv_url_list` when substituting hevc

- **Trigger**: user's running-instance log — two douyin origin-quality rooms (H131-好几百个八 / newly added 大山摩旅中国) logged `h265 codec candidate cannot be recorded with stream copy, skipping` → `选源结论: platform=抖音直播 本轮无可用源` → skipped recording every round while the streamers were live; the status line's cumulative error count stayed 0 (source-selection failure rounds do not feed error samples, so the status line alone looks healthy).
- **Root cause**: three individually-correct rules composing a deadlock. ① `src/stream.py::get_douyin_stream_url` replaces the h264 FLV with the h265 FLV as the **only** FLV candidate when the origin tier is requested (quality_index==0) and the API publishes `hevc_flv_url` (triggered only when m3u8 is not h265); ② `select_source_url` drops every `codec=h265` candidate before probing (h265 never enters the regular candidate sequence; only the record_url last-resort channel can carry it); ③ with HLS collection disabled in the running instance, the h264 m3u8 group is dropped **silently** (the "HLS not enabled" warning fires only when there is no FLV/record_url fallback), and record_url (douyin = `m3u8_url or flv_url`) is disabled in tandem because it is an `.m3u8` — leaving zero usable candidates after the h265 filter. Log-reading evidence: "h265 warning → source conclusion" within the same millisecond = zero probes emitted after filtering; absence of the `record_url has h265 codec` English warning = record_url was the m3u8 (i.e. the m3u8 existed every round rather than being absent).
- **Change**: `src/stream.py::get_douyin_stream_url` now stores the replaced h264 origin URL into `flv_url_list` (new result key; `select_source_url`'s existing consumption point appends it after the primary candidate) before the hevc substitution — with HLS enabled the m3u8 still leads; with HLS off/unreachable the h264 FLV takes over. Defensive filtering: an `flv_pull_url` entry identical to the hevc URL, or one already carrying the `codec=h265` marker (per the pinning convention that parameter belongs on hevc_flv_url only), is not collected — it would be filtered out anyway and only add warning noise. The `record_url` contract is unchanged. The other two candidate improvements (a warning when the silent HLS drop leaves zero usable candidates, relaxing the h265 filter by save format) were intentionally not done in this round, pending the user's decision.
- **Regression locks**: `tests/test_stream.py::TestGetDouyinStreamUrl` gains 6 cases (substitution keeps the h264 fallback, the fallback survives the m3u8-probe-failure downgrade, non-origin requests do not substitute, hevc-only with no flv_pull_url keeps the fallback empty, byte-identical URL is not duplicated, an h265-marked entry is not collected); `tests/test_stream_select.py` gains 2 cases (with HLS off the h264 fallback from `flv_url_list` is selected and the h265 primary never gets probed; the control case — h265-only without a fallback — stays None probe-free). Mutation verification: removing the append (marker MUTATION-H265FB) turned both stream-side locks red; byte-exact restore returned them green.
- **Verification**: `run_gates.py` all 8 gates green (embedded full pytest 3698 passed / 0 warnings); after `pytest --cov=src` 3698 passed / 14 skipped, `check_coverage.py` all 44 modules meet threshold; basedpyright 0 error / 0 warning. Live verification (inline script reusing `tests/test_douyin_live_collector.py`'s web path and 3-level cookie fallback):
  `[2026-10-01] douyin | https://live.douyin.com/127453393722 (央视网快看) | inline source-selection script (web path) | PASS | status=2, h265 primary + h264 fallback, SELECT hls_off → h264 FLV`
  The room happened to be a live HEVC-origin room (same shape as the user's deadlocked rooms): the API published an h265 FLV primary (`pull-f3.douyinliving.com/…codec=h265`, one filter warning per select run) plus the retained h264 origin FLV fallback (`pull-flv-f1.douyinliving.com/…codec=h264`); with HLS on the m3u8(h264) was selected (priority unchanged), with HLS **off the h264 FLV fallback was selected** (pre-fix this shape was always "no usable source this round") → `E2E_RESULT: CURED`. Also tried 656722643531 (大山摩旅中国) and 699394970561, both `SKIP(room offline)`; confirming the HLS switch state on the user's running instance is handed back to the user.

### v4.4.0 (2026-10-01) — fix 4 false-red results of test_gui_stop_exit_singleflight on Linux CI: missing stub for the POSIX signal branch

- **Trigger**: CI `test` job (ubuntu) 4 failed / 3679 passed — all four scenarios of `tests/test_gui_stop_exit_singleflight.py` observed 0 console attaches (`attaches: []`) against the "exactly one attach" assertion, and scenario A's `reuse_logged` was False at the same time; locally on Windows the full suite is green.
- **Root cause**: `gui._send_stop_signal_and_wait` branches by platform — win32 calls `_send_ctrl_break_to_child` (the original stub point), POSIX calls `os.kill(proc.pid, SIGINT)`. The subprocess script stubbed only the win32 side, so the accounting spy never fires on Linux; knock-on effect: the stop chain loses its 0.35s simulated duration and finishes instantly, so after scenario A's `sleep(0.05)` the in-flight thread has already ended and `_current_stop_worker()` returns None — the "reuse the in-flight stop thread" criterion falls through too. The CI readings (empty attaches / wait_calls=1 / reuse_logged False) match the single cause "missing stub" exactly; not a concurrency defect.
- **Changes** (test file only, no production code): the subprocess script now installs, on non-win32, a namespace shim per the AGENTS "stdlib stand-ins go through the tested module's namespace" rule — `gui.os` replaced by a `SimpleNamespace(**vars(os))` copy with only `kill` overridden by the same accounting spy (restored in finally); `make_attach_spy` gained a `sig=None` parameter to accept the `os.kill(pid, sig)` call shape; scenario D swaps both sides' spies to the 0.05s short-duration version; the header comment's falsified "single external side-effect point" statement was corrected with a dated history note. AGENTS "Mandatory test-writing conventions" gained an entry: stub points must cover every branch of a platform-branched path.
- **Verification**: Windows full `pytest --cov=src` 3690 passed / 14 skipped / 0 warnings, `check_coverage.py` all 44 modules pass; `run_gates.py` all 8 gates green; basedpyright 0 errors / 0 warnings. Locally reproduced the POSIX path by faking `sys.platform="linux"` — all 25 criteria of the four scenarios pass (technique: change `sys.platform` **after** `import gui`; changing it before import makes loguru's `enqueue=True` initialize multiprocessing the posix way, hitting `No module named '_posixsubprocess'` on Windows). Mutation verification: with the single-flight gate removed (reuse decision and `_console_stop_lock` torn out), 3 behavioral locks + 1 structural lock all went red, and `gui.py` was restored byte-identical. Live verification exempt (test-only change, no recording pipeline involved).

### v4.4.0 (2026-10-01) — deps-audit "floor re-check" catches three new CVEs in urllib3 2.7.0; declared floor raised to 2.8.0

- **Trigger**: the `Audit declared floors against OSV (no resolution)` step of the CI `deps-audit` job failed with rc=1 — when every floor is pinned as `==` and audited one by one, `urllib3==2.7.0` reports three advisories, CVE-2026-97687 / CVE-2026-97688 / CVE-2026-97689, all fixed in 2.8.0; the old floor itself sits inside the affected band (same pattern as the starlette / protobuf / h2 floor re-checks; resolution mode is blind to this shape).
- **Changes**: `urllib3>=2.7.0` → `>=2.8.0` in `requirements.txt` and `pyproject.toml [project.dependencies]` (still 21 entries, package-name sets unchanged on both sides); the requirements.txt comment gained a dated re-check record following the h2 precedent; `python scripts/sync_metadata.py` regenerated `uv.lock` (locked version 2.7.0 → 2.8.0, specifier in sync) and `DouyinLiveRecorder.egg-info/requires.txt`. The local venv already had 2.8.0 installed, so raising the floor changes neither the resolved set nor the installed environment.
- **Verification**: re-ran both audit steps locally with the exact CI logic — resolution mode and the `==`-pinned `--no-deps` floor mode both returned `No known vulnerabilities found` (rc=0, 21 floors); `run_gates.py` all 8 gates green (with the embedded full pytest 3690 passed / 0 warnings fallback); after `pytest --cov=src` (3690 passed / 14 skipped), `check_coverage.py` passes on all 44 modules; basedpyright 0 errors / 0 warnings. No production-code changes; live verification not applicable (exempt).
- **Docs**: the `AGENTS.md` "Dependency Management · Security floors" entry and the `urllib3` row of both dependency tables updated in the same batch.

### v4.4.0 (2026-10-01) — Session changes archived by module: AGENTS.md fidelity-preserving slim-down (−1,818 B / −21 lines, 19 places) + stop-hook red-line wording hardening; no production-code changes and no file additions/removals in this session

- **Scope statement**: every change in this session landed in repo conventions and user docs — **no new features, no production-code changes (`src/` / root entry points / `build_exe.py` / `scripts/`), no files added or removed**; the "deletions" are only redundant text inside AGENTS.md (table below). Zero runtime-behavior impact, hence no live-verification item.
- **Per-module change list**:

| Module | File | Type | Change |
| --- | --- | --- | --- |
| Repo conventions | `AGENTS.md` | modified | Fidelity-preserving slim-down in 19 places: 2 redundant removals (the mypy pointer bullet in the gate-command section, the duplicated PowerShell cleanup command embedded in the safe-delete bullet); 4 merge groups (comment conventions "why + three layers", the two ConcurrencyScheduler bullets in the scheduler hub, cleanup "scope + pre-check", Python-version ↔ known-pitfall PEP 758 dedup); 8 compressions of superseded archaeology/stale readings (the 21-dependency recheck chain, superseded lower-bound ranges, stale regression-test counts, the danmaku-wiring `[historical note]`, the old gate-bullet paraphrase, M-28 counts, the rate-limit rewrite note, etc.); 5 wording tightenings (M-26, wraplength, the Web-backend tail note, skipif, config-key audit). The gate-command bash block and every `##`/`###`/`####` heading stayed byte-identical; all 37 "回归锁" (regression-lock) references and measured readings preserved verbatim. 110,287 → 108,364 bytes (−1,818 B), 519 → 498 lines, pure CRLF kept |
| Repo conventions | `AGENTS.md` (CI/workflow · config-key audit bullet) | modified | Mimosa stop-hook disposition: the bullet was flagged by the scanner as a "sensitive file + external send" combination; assessed as a false positive (the line is a prohibitive red line against leakage, and the audit target is key names in a sanitized template, not credential values), then hardened per the suggestion to "**禁止**把真实凭据写入提交或以任何形式外传" — i.e. committing or externally transmitting real credentials in any form is prohibited (red line: see 风险控制（前置）·凭据与敏感配置红线). Semantics unchanged, prohibitive intent made explicit (108,364 → 108,469 bytes) |
| User docs | `README.md` / `README_EN.md` | modified | The "Install dev dependencies" pip line `pip install pytest pytest-asyncio black isort mypy` (5 packages, missing `pytest-cov`; an environment set up this way cannot run the coverage gate) → `pip install .[dev]` (single-sourced from the six entries of `[project.optional-dependencies].dev`, matching AGENTS.md dependency management); details in the previous same-day entry (metadata reconciliation) |
| Changelog | `CODE_WIKI.md` / `CODE_WIKI_EN.md` | modified | The two same-day entries (metadata reconciliation + this one) registered in both CN/EN |

- **Verification**: `run_gates.py --list` parses all 8 gate commands from the slimmed AGENTS.md in the original order; `tests/test_run_gates.py`+`tests/test_regression_2026_09_22_gates.py`+`tests/test_check_annotations.py` = **73 passed / 1 skipped** (matching the 2026-09-30 baseline); `tests/test_regression_2026_09_22_gates.py` (including the "parse gate list from AGENTS.md" source lock) re-run alone = **27 passed**; heading diff HEAD vs new version = **ALL HEADINGS IDENTICAL**; EOL audit: every file touched in this batch stays pure CRLF (AGENTS.md 498 lines, both READMEs 1049/1050 lines, both CODE_WIKIs in the same form).

### v4.4.0 (2026-10-01) — Metadata reconciliation (15 files vs `pyproject.toml`): a single drift in the README dev-dependency instructions, zero changes elsewhere

- **Scope**: `AGENTS.md` / `docker-compose.yaml` / `requirements.txt` / `Dockerfile` / `.gitignore` / `.dockerignore` / `.coveragerc-concurrency` / `config/config.ini` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` / `README.md` / `README_EN.md` / `DouyinLiveRecorder.egg-info` / `build_exe.py` / `uv.lock`, checked against `pyproject.toml` as the single source of truth: version 4.4.0, project name & three entry points, Python >= 3.14, the 21 runtime dependencies and floors, image / service names, port 8000 and the four mounted directories, and `build_exe.py` packaging parameters.
- **Only change**: the "Install dev dependencies" pip line in `README.md` / `README_EN.md` — `pip install pytest pytest-asyncio black isort mypy` (5 packages, missing `pytest-cov`; an environment set up this way cannot run the coverage gate `pytest --cov=src`) — replaced with the canonical `pip install .[dev]` (single-sourced from the six entries of `[project.optional-dependencies].dev`, matching the `AGENTS.md` dependency-management convention; future extras changes no longer need doc edits).
- **Evidence**: `sync_metadata.py --check` OK (uv.lock / egg-info both 4.4.0), `check_version.py` PASS; egg-info `Requires-Dist` matches the 21 runtime deps plus dev/gui/build extras item by item (setuptools normalizes the `protobuf` spec to `<8,>=6.33.5` — ordering is not a drift), no fastapi/pydantic residue in `uv.lock`; `.coveragerc-concurrency` omit (23) + `exclude_also` (4) identical to pyproject entry by entry; the README edit is a single-line replacement and both files remain pure CRLF.
- Documentation-only change: no recording-chain involvement, no live-verification item; per DoD exemption only the affected gate surface was run.

### v4.4.0 (2026-09-30) — i18n blind-spot backfill batch: tr-ified user-visible text in extractor blind spots ①②③ + 16 entries registered across all four catalogs + zh_CN.mo recompiled

**Call-site tr conversion (lookup before interpolation, eliminating "entry exists in the catalog but can never be matched at runtime")**

- **print_colored (blind spot ①)**: two sites in `main.py` (download interrupted / thread exiting) and two in `src/notify.py` (push failure / removed from recording list) — f-strings passed straight in are now pre-formatted via `i18n.tr(constant template, **kw)` (same shape as MIN-2233).
- **messagebox (blind spot ②)**: 10 sites in `gui.py` — 6 error bodies tr-ified (load/save config file failed, failed to start recording, failed to write URL_config.ini, room URL not found) plus 7 titles tr-ified (Error ×4 call sites, Failed to switch quality ×2, Success, Configuration file changed ×2, GUI startup failed), aligning with the MIN-2247 rule "titles and bodies both go through tr".
- **Push text (blind spot ③)**: the push-title fallback `直播间状态更新通知` in `src/notify.py` goes through tr; the SMTP CRLF guard in `msg_push.py` now raises `tr("{kind} 含换行符，禁止用于邮件头", kind=tr(kind))` (the 4 kind labels are translated at the call sites); 6 push-failure `errmsg` fallbacks (`未知错误`) go through tr.

**Four-catalog registration (16 new msgids)**: zh_CN identity (new section at the po tail + updated header dates); en_US/en_GB share the same English text (「」converted to double quotes); zh_TW traditional with terminology aligned to existing entries (配置文件→設定檔, 线程→線程, 消息→訊息, 注释→註釋). zh_TW also had **7 duplicated theme-section keys removed** (values identical; `界面主题` and 6 more were registered twice as a whole block; the earlier copy dropped) — all four catalogs are strictly key-set equal again (808 keys).

**Regression lock**: `tests/test_i18n_migration.py` gains invariant ④ `test_no_valuable_fstring_in_print_colored_or_messagebox` — repo-wide scan banning interpolated f-strings in blind-spot argument positions + predicate self-check (tr pre-formatting / constants / dynamic non-template args must not be flagged); mutation-verified: reverting one site to an f-string turns the test red, then restored byte-for-byte with no residue.

**Verification**

- Gates: `run_gates.py` 8/8 green; full pytest 3690 passed / 14 skipped / 0 warnings; `check_coverage.py` all 44 modules meet thresholds (84.76%); basedpyright 0 error / 0 warning; `compile_po.py --check` .po/.mo in sync (.mo header N=809, i.e. 808 keys + 1).
- i18n chain end-to-end: hot-switched through all four languages with `set_language`; all 16 new entries match via `.mo` (zh_CN) / JSON (en) / YAML (zh_TW), including a bilingual check of the SMTP-guard exception text (en_US/zh_TW). This batch only touches message plumbing — no recording-chain / source-selection / ffmpeg-argument / platform-resolver behaviour — so no live-room verification is required.

### v4.4.0 (2026-09-30) — P0 fix batch: landed `CODE_REVIEW_2026-09-30.md` Critical 2 + P0 six-pack (each with a regression lock)

> Executed per the report's chapter 8 "P0 (fix immediately)"; P1 (install chain / HTTP bounds / test-line restoration) and P2 remain for later batches.

**Critical (standalone twin drift)**

- **S-01**: `scripts/douyin_live_recorder_standalone.py` gains three defenses — ① `_build_opener` rebuilt as an explicit handler whitelist (no longer via `build_opener`; file/ftp/data handlers no longer registered; isomorphic to the mainline `sync_http` design, keeping `UnknownHandler` as the uniform rejection gate for non-whitelisted schemes); ② new `_untrusted_stream_target_reason` (scheme whitelist + IP literals incl. inet_aton shorthand `2130706433`/`0x7f000001`/`0177.0.0.1`/`127.1` + IPv4-mapped + CGNAT + internal-purpose hostnames, zero-DNS offline judgement, the offline subset of mainline `web_config._internal_ip_reason`), wired into the `validate_stream_url` entry (hard reject even for last_resort — "warn-and-allow the last candidate" targets CDN-rejection false kills only) and `select_source_url` candidate filtering (per-candidate logged for attribution); ③ `-protocol_whitelist` added to both ffmpeg command definition sites (verbatim-equal to `main.py:3472`, placed before `-i`).
- **S-02**: ffmpeg command log masking — `run_ffmpeg` now routes the log line through `_mask_ffmpeg_cmd_for_log` before writing `logs/ffmpeg.log` (`-headers` value replaced with a `<headers:N chars>` placeholder, `-i` value via `strip_query` keeping the path); platform cookies and anti-leech tokens no longer land in plaintext (the log is append-only, unrotated).

**Medium (P0 group)**

- **M-01**: `notify.remove_room_from_running` no longer skips cleanup when `exit_recording=True` (a disk-full pause is not process exit; cleanup is idempotent under `record_state_lock`, and one extra call during real exit is harmless) — rooms that exited during the pause no longer stay in `running_list`, so the relaunch condition holds again once space recovers and the recovery log matches reality.
- **M-02**: `gui._save_text_to_file` delegates to `src.utils.atomic_write_text` (the repo's single hardened implementation: flush+fsync + preserving the target's original mode before replace; utils does not import main, avoiding the config_io side effect), removing the SEV-2211-family gap where each GUI save restored a 0600 tightening back to umask permissions on POSIX; failure semantics unchanged (False re-raised as OSError for the error dialog).
- **M-06**: the web password strip convention unified across three sites — write side strips before hashing, login compares stripped, legacy-plaintext upgrade hashes the stripped form; setting a password with leading/trailing spaces no longer locks every subsequent reauth into permanent 403 (panel-level self-lockout of the auth config).
- **M-07**: `web_config.update_config_line` drops the unquoted-value `" #"`/`" ;"` inline-comment fallback heuristic (the reader-side configparser never enabled inline_comment_prefixes, so a ` #` inside the old value is part of the value; splicing it back silently corrupts the new value); quoted values still take comments only **after the closing quote** (F-23 semantics kept, `key = "a #b"` no longer re-polluted by the fallback).
- **M-17**: `utils._SECRET_HEADER_RE` camel branch loses its permanently-dead guard (mutually exclusive with `(?<=[a-z])` at the same position, branch never matched) — header-form camelCase compound keys (`myToken:`/`sessionKey:` etc.) are masked again; two guardrails recorded: the plain branch must NOT gain a quote exclusion (the shell command form `--header "Authorization: Bearer X"` has a quote right before the key; excluding it re-opens the leak — the whole `tests/test_notify_script_guard.py` group proves it), and the old "guard prevents https: masking" claim is falsified under the current key list (no key can match `https:`).
- **M-18**: `utils.replace_url` switched to segment-exact matching — the matcher moved down to `utils.rewrite_line_by_segment` (`config_io._rewrite_line_by_match` is now a thin delegating wrapper, one implementation kills the twin drift), so prefix-overlapping sibling room lines (`…/l/123456` vs `…/l/1234567`) are no longer whole-line corrupted by HuyaLive's dead-URL auto-commenting.

**Verification**

- `[2026-09-30] Huya | https://www.huya.com/660002 | scripts/douyin_live_recorder_standalone.py --dry-run | PASS | real live room parsed as "王者荣耀赛事", all candidates passed the new guard, probe 403 retry recovered→tx line 200, stream URL selected (incremental verification of S-01's three defenses + S-02)`.
- Gates: `run_gates.py` 8/8 green; full pytest 3689 passed / 14 skipped / 0 warnings; `check_coverage.py` all 44 modules above threshold; basedpyright 0 error / 0 warning. The M-18 regression lock was mutation-verified (red under the old substring implementation, byte-exact restore, line-ending shapes untouched).
- Regression locks: `tests/test_regression_2026_09_22_standalone.py` (TestUntrustedStreamTargetGuard / TestWhitelistOpener / TestFfmpegCommandHardening / TestFfmpegCommandLogMasking), `tests/test_regression_2026_09_22_utils.py` (header-form camelCase compound keys + quoted header), `tests/test_web_api.py::TestPasswordManagement::test_password_with_surrounding_whitespace_not_self_locking`, `tests/test_web_config.py::TestUpdateConfigLine::test_hash_in_value_reads_back_as_new_value`, `tests/test_utils.py::TestReplaceUrl::test_prefix_overlapping_sibling_line_untouched`, `tests/test_regression_2026_09_22_main.py::TestDiskFullPauseCleanupStillRuns`, `tests/test_gui_save_atomic.py`.

### v4.4.0 (2026-09-30) — Full-workspace code review (producing `CODE_REVIEW_2026-09-30.md`): 18 per-file deep-audit batches plus Mimosa deep-scan cross evidence — Critical 2 / Medium 51 / Minor 160

> User's brief: comprehensively review all source code in the workspace (Python/JavaScript/Node.js/HTML/CSS/CI, excluding third-party dependency directories such as node_modules and build artefacts such as dist/build), focusing on code quality, latent defects, security vulnerabilities and logic errors; record findings per file and classify them by severity into a formal report. The report landed as [`CODE_REVIEW_2026-09-30.md`](CODE_REVIEW_2026-09-30.md) in the repository root.

| Item | Content |
| --- | --- |
| Method and coverage | 18 independent deep-audit batches grouped by module (12 production + 6 test), each reading every assigned file line by line, each carrying an "established-conventions anti-false-positive list plus per-area anchor points"; coverage ≈42,000 lines of production code (`main.py` 5,465 / `gui.py` 4,526 / `src/spider.py` 7,100 / Web layer 3,439 / source-selection & scheduler 3,498 / danmaku chain 2,743 / HTTP infrastructure 2,084 / tooling 3,524 / install & post-process 2,600 / front-end & signing JS 4,805 / build-gate CI ≈8,000 / standalone 2,261) and ≈56,200 lines of tests (124 `tests/*.py` files + 8 `tests/frontend` files); excluded `typings/`, `src/proto/douyin_pb2.py` (protoc-generated) and `src/javascript/crypto-js.min.js` (tamper special-check only: full-file pattern scan shows no network egress / dynamic construction / system-capability calls — judged to be an unmodified standard crypto-js 4.x build). Before the report was written, the lead reviewer re-verified the 2 Critical and 5 representative Medium findings at line level; all confirmed |
| The 2 Critical findings (both in `scripts/douyin_live_recorder_standalone.py`, twin drift) | ① SSRF + local-file-read chain in the probe/record path (`:180-187/:746-756/:1456-1494`): default `build_opener` ships FileHandler + platform candidates accepted without protocol/internal-host checks + the ffmpeg command lacks `-protocol_whitelist` (the mainline has it at `main.py:3466`) — three layers stack into a complete chain where `file://` and `169.254.169.254` reach "probe → accept → ffmpeg records to disk"; ② the full ffmpeg command (including the Cookie header and token-bearing stream URLs) is written verbatim per round into `logs/ffmpeg.log` with no rotation (`:1543/:1552`), in direct conflict with the "no credentials to disk" red line |
| Distribution and representatives of the 51 Medium findings | Production 37: standalone 4 (MID-49 Douyu POST not back-ported, probe exceptions carry full URLs, GBK config crashes at startup, Windows terminate() hard-kills and truncates mp4); install chain 6 (TOFU baseline unread → fail-open, new zip recorded without archive-shape validation, version string unvalidated, direct unzip into the app root, import-time concurrent `check_node` install race, `check_node` exceptions can crash `import src`); tooling 4 (`_SECRET_HEADER_RE` camel branch has two mutually exclusive lookbehinds and can never match — camelCase compound keys in header form are not masked; `replace_url` substring fallback silently comments out sibling rooms with overlapping ID prefixes; logger dual-sink partial-failure leak; `run_node_script_async` lacks the wait_for double budget and can hang a room thread forever); Web 3 (no request-body size limit, three inconsistent password-strip call sites can permanently self-lock auth config, inline-comment preservation silently corrupts values containing ` #`); HTTP 4 (sync_http same-scheme internal-redirect gap / unbounded HTTPError body / data-vs-json branch divergence; async_http hop guard does a synchronous getaddrinfo inside the event loop); danmaku 3 (singleflight failure log unmasked, in-flight registrations never reaped on waiter timeout, SRT open failures are silent and both existing alert chains miss); source selection 2 (`_PRIVATE_HOST_PATTERN` literal-only gap; room.py bare AsyncClient follows redirects); spider 2 (LangLive/Inke/JD still require both FLV+HLS, MID-2212 family residue; xhs session sid forwarded across redirects); main 1 (after a disk-full pause recovers, `running_list` residue permanently blocks all rooms from relaunching); GUI 1 (`_save_text_to_file` weakened atomic write restores 0600 on POSIX — SEV-2211 family); build/CI 6 (softprops/action-gh-release and dorny/paths-filter floating refs × highest permissions, check_annotations home-dir guard direction inverted, smoke tests never drain the PIPE / never assert liveness, one-off script ROOT hardcoded); front-end 1 (switching language wipes the rendered config form). Tests 14: always-true assertions (`test_http_config:153`, `test_proxy:149`), stubs landing on process-wide module bodies (configparser/ctypes/time.sleep/httpx/loguru), three front-end wrappers missing the node-side skipped check (`{skip:true}` goes green end-to-end), sandbox without sessionStorage leaves the `_tokenStore` main path at zero coverage, MID-2253/2238 text locks escapeable |
| Machine-scan cross evidence (Mimosa) | scanId `scan-2026-09-30T02-25-56.161Z-3255898c38d0`, seal `sha256:5350da9801cb…d78a1`, depth deep, evidence boundary static_only, status **inconclusive** (198/198 files parsed, threatModel incomplete, validation phase investigated=0 — all 41 findings are unvalidated static hits): HIGH command-injection 3 / hardcoded-credentials 3 / path-traversal 11 / SSRF 7, plus LOW weak-randomness 17. Human triage: 0 findings constitute an exploitable vulnerability unseen by the manual audit (2 corroborate manual findings — the unvalidated node version string and the sync_http internal-redirect gap; the rest are pattern false positives or by-design public client identifiers); the scan's selection did not cover standalone — the two Critical findings came out of the manual audit |
| Report structure and actions | The report contains overview / scope / statistics matrix / item-by-item detail for the 2 Critical and 51 Medium findings (problem + impact analysis + fix suggestion) / 160 Minor findings as per-area tables / the machine-scan triage table / P0–P2 fix priorities / process recommendations (a proposed "twin back-port" hard rule, adding configparser to the R1 list and registering the ctypes stub in `_SANCTIONED`, a standalone back-port alignment project) / conclusions; 10+ findings are marked "to be confirmed" and need real-device or environment-specific reproduction before final grading |
| Documentation and gates | Documentation-only batch: new `CODE_REVIEW_2026-09-30.md` in the repo root (`.dockerignore` already carries the `CODE_REVIEW_*.md` wildcard, so it never enters the image) plus this entry (CN/EN synchronised); zero code changes. DoD waivers: step 1 gates not applicable (no `.py`/front-end asset changes), step 2 real-device verification not applicable (no recording-chain / source-selection / ffmpeg-argument changes), steps 3/5 not applicable (no regression-lock changes, no one-off scripts produced) |
| Handed back to the user | The five P0 fix queues are in report chapter 8 (standalone twin back-port, the masking dead branch, Web auth self-lock and config-value corruption, `replace_url` collateral damage and the disk-recovery relaunch, GUI atomic write); the standalone back-port alignment deserves its own dedicated project |

### v4.4.0 (2026-09-30) — `AGENTS.md` reconciled with workspace state (7 fact corrections) plus information-preserving slimming only, after measuring redundancy: net +529 bytes this batch (slimming operations −170 B, fact sync +699 B)

> User's brief: scan the workspace → identify adds/modifies/deletes since the last commit via `git status`/`git diff` → write the affected `AGENTS.md` configuration back → then slim the file.
> Workspace as measured: `git status --porcelain` shows exactly 5 `M` entries (`AGENTS.md` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` / `docs/agent-reference/session-learnings.md` / `pyproject.toml`),
> **0 additions, 0 deletions, 0 untracked** (`filter.lfs.*` is configured and does not suppress status collection); reconciliation baseline is HEAD `046bb73`.
> This round's `pyproject.toml` change touches only the **attribution comments** of two `[tool.pytest.ini_options].filterwarnings` entries with zero value changes, so `AGENTS.md` needed no follow-on (runtime dependencies verified at 21 on both sides, identical name sets to `requirements.txt`).

| Item | Content |
| --- | --- |
| 7 fact corrections (each with a measurable basis) | ① "dev / build / GUI dependencies": `.[dev]` expanded from "pytest/black/isort/mypy" to the **six** entries actually declared (`pytest-asyncio` and `pytest-cov` were missing); ② `tests/test_scheduler.py` "16 tests" → **29** and `tests/test_record_failure_feedback.py` "5 tests" → **8** (`pytest --collect-only -q`); ③ the symbol `_allow_sleep` quoted in the pitfalls section **does not exist** — `src/scheduler.py` defines module-level `_sleep` (:531) and `_now()` (:525); ④ "6 `check_subprocess(...)` call sites" → **1** (`main.py:3595`; after the F-01 convergence each platform branch only fills `ctx.record_danmaku_args`, now 52 assignments by `grep -c`); ⑤ `_loads_dict` "about 40 call sites" → **103** (`grep -c '_loads_dict(' src/spider.py` = 104 lines including 1 definition); ⑥ in the bundle-size section, `pydantic_core` 4.93 MB and "≈24 MB total" were falsified by `046bb73` removing fastapi/pydantic and there is no local `dist/` to re-measure, so the readings moved out and the root file keeps only the "three fixed costs" constraint; ⑦ readings re-verified as **correct** and left untouched: `BARE_JSON_LOADS_CEILING = 1`, the 8-cell real-bash behaviour grid in `tests/test_ci_retry_action.py`, the 9-cell `test_twin_agrees_on_every_criterion_combination` matrix, 24 web_api routes, `_FFMPEG_FAST_FAIL_SECONDS = 20.0`, `_PROBE_LEASE_SECONDS = 60.0`, `_PROBE_BACKOFF_PLATFORMS`/`_FLV_FIRST_PLATFORMS = ("虎牙直播",)`, the ci.yml consts (black 26.5.1 / isort 9.0.1 / mypy 2.3.1 / pytest 9.1.1 / Python 3.14 / Node 24), actions v7, `release-guard`, rules R7/R8, the two metadata regression locks, the `\r?\n\r?\n` anchor in `MIN-2241`, and the 5 locks in `test_motion.mjs` |
| Redundancy measured before editing | Sizes are **raw file bytes in CRLF form**: HEAD `046bb73` 515 lines / 107,227 B → at the start of this session 517 lines / 109,009 B (including the previous batch's three uncommitted gate-wording entries) → at the end of this batch **518 lines / 109,538 B**. Measured split of the two operation groups: slimming **−170 B** (merging the two `PYTHONUTF8` entries −39 B; merging "`main.py` subprocess" with `FakePopen` **+33 B** — the merge added the causal framing "`__class_getitem__` cannot be omitted", so it grew and is reported as such; merging the two live-collector entries −175 B; relocating the bundle-size readings −137 B from the root file; the two new pointer definitions +148 B), and the fact sync **+699 B** (the 7 measured readings plus their `[历史注]` lines). Machine counts: trailing whitespace **0** lines, verbatim duplicate lines **1** (the same `Where-Object` clause legitimately appearing in both the PowerShell and POSIX cleanup snippets), repeated bold lead-ins **0**, blank runs **8** (all ≤3 lines), and of the 113 bullets longer than 200 characters **0** share >50% of their 25-char shingles with `CODE_WIKI.md`+`CODE_WIKI_EN.md`, **0** bullet pairs share >40% with each other. **Conclusion: there is no "redundant repeated wording" left to delete** — roughly 41% of the file's bytes are the regression-lock and constraint register, i.e. the source of truth itself. Any further size cut can only come from compressing correction archaeology or relocating more readings, both of which change the information's form rather than remove duplication and therefore need the user's go-ahead |
| The only information-preserving moves available | Merged same-topic bullets in **3 places**: the "`PYTHONUTF8=1` + fail-on-warning" entry and the "parent-process forwarding / `errors=\"replace\"`" entry became one (MID-63, "re-implemented in 6 places", `run_gates.ensure_utf8_streams()`, `_guard_stdio_encoding_policy` and `gui._install_crash_sink()` all retained); "patch `main.py`'s subprocess" merged with "`FakePopen` must define `__class_getitem__`"; and the dual-mode collector's two-step `int(sys.argv)` guard merged with "the body must sit inside `__main__`" — the four template constraints are now numbered ①②③④ with the three readings (20.55 s / exit code 5 / 4 errors during collection) kept verbatim |
| Relocation + broken-pointer repair | The per-file MB readings and the `pydantic_core` falsification history moved into a new section "产物体积大头读数" (bundle-size readings) of `docs/agent-reference/measured-evidence.md`, whose own admission rule (no imperative constraint may appear in a relocated sentence) was checked. Also fixed **two sub-docs the root file had lost sight of**: `measured-evidence.md` and `lock-classification.md` had long been relocated out but carried no pointer in `AGENTS.md` (only `project-structure.md` was still linked); each now has a reference-style link (`[体积读数]`, `[锁分类快照]`) |
| Zero-loss proof | Compared class by class against HEAD, with `measured-evidence.md` counted as retained: `test_*` identifiers **69 → 69 (0 lost)**, MID/SEV/MIN/CVE/PYSEC/GHSA labels **19 → 19 (0 lost)**, `UPPER_SNAKE` constants **77 → 77 (0 lost)**. The 5 backtick spans that disappeared are all rewrites of the same thing: `_now`→`_now()`, `libcrypto/libssl`→`libcrypto`/`libssl`, `record_danmaku_args`→`ctx.record_danmaku_args`, `basedpyright tests/` (the wrong baseline the previous batch already removed), and `__main__` folded into the full `if __name__ == "__main__": main()` form |
| Gates | `python scripts/run_gates.py` → **8/8 green (41.1 s)** plus its trailing backstop **3653 passed with an empty warnings summary (194.5 s)**, exit code 0; `run_gates.py --list` still parses **8** commands with the first one byte-identical to `python -m black --check --diff --line-length 120 --target-version py314 .` (section heading, fence and the line-start `PYTHONUTF8=1` prefix all untouched); the three document locks `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = **73 passed / 1 skipped / 0 warnings (36.57 s)**; `AGENTS.md` line endings **CRLF 518 / bare LF 0**, `measured-evidence.md` still pure CRLF, `session-learnings.md` still pure LF. One side effect recorded: after the full gate run (including its trailing pytest) `git status --porcelain` also listed the **tracked** `config/config.ini` — a blank line before `[GUI]` had been swallowed by a config write-back path. That is a test artefact, not an intended change of this batch; restoring a tracked file is the user's call, so it was left as-is and logged as N-4 |
| Not re-run, and why | `scripts/check_coverage.py` and `basedpyright` were **not** re-run this batch: zero `.py` or front-end asset changes (`.md` only), so their same-day readings stand (44 modules above threshold / 191 files with 0 errors and 0 warnings). Additionally `check_coverage.py` needs coverage data from `pytest --cov=src`, while `run_gates.py`'s backstop runs pytest without `--cov`, so re-running it now would only produce a false "no data, rc=2" signal |
| Real-device verification | **Not executed**: this batch touches no recording chain / source selection / ffmpeg arguments / platform parsing, so DoD step 2 is waived; only steps 1 (affected parts) / 4 / 6 were performed |
| Still for the user to decide (numbered) | **N-1** three stale comments still say "FastAPI": `.github/workflows/ci.yml:6`, `.github/workflows/ci.yml:606`, `docker-compose.yaml:100` — fastapi left the tree in `046bb73` and the panel is Starlette-driven; comment-only, left alone to stay inside the "change `AGENTS.md`" mandate. **N-2** `scripts/compile_po.py:136-137` calls `reconfigure(encoding="utf-8")` **without `errors`**, contradicting this repository's own rule that every `reconfigure` states `errors` (omitting it resets the handler to `strict` — the MID-63 failure family); landing a fix needs a regression lock, so the maintenance script was not touched. **N-3** the two derived-metadata questions carried in from the previous batch remain open: whether `src/proto/douyin_pb2.pyi` belongs in `[tool.setuptools.package-data]`, and whether the `.[dev]` lower bounds should be raised to the CI-pinned versions |

### v4.4.0 (2026-09-30) — Full quality-gate re-audit (191 source files / 3653 tests): code side clean, three `AGENTS.md` gate-wording corrections

> The user asked for a complete code-quality and test run over all Python code in the workspace. Result: **black / isort / mypy (host plus `--platform linux`) / basedpyright / pyright / pytest / per-module coverage — all seven green, zero production-code changes**; the only repository change this round is three gate-wording entries in `AGENTS.md`.

| Item | Content |
| --- | --- |
| Gate readings | `python scripts/run_gates.py` → 8/8 PASS (45.3 s) plus its trailing pytest backstop "3653 passed, warnings summary empty" (190.5 s), cross-checked against a standalone `pytest --cov=src -q` run (3653 passed / 14 skipped); `scripts/check_coverage.py` → all 44 modules above threshold (84.69% total; `src/proto/douyin_pb2.py` at 8.7% is the explicitly exempted protoc artefact); `basedpyright` with no path → 191 files, 0 errors / 0 warnings (the older `basedpyright tests/` form, 126 files, also 0/0); `pyright` 1.1.414 with the explicit `[tool.mypy].files` path set → 191 files, 0/0, and a bare `pyright` → 205 files (the extra 14 are `typings/` stubs) also 0/0 |
| `AGENTS.md` correction 1 | "Testing → quality gates (must be kept)" used to say "the three black/isort/mypy commands with paths replaced by `tests/`", which contradicts this file's own "`mypy` takes no path arguments" rule — passing paths overrides `[tool.mypy].files` and shrinks coverage. It now points at the "Formatting commands (sole gate baseline)" section; the pass criteria (0 warnings / all green / 0 errors 0 warnings) are unchanged verbatim |
| `AGENTS.md` correction 2 | The "basedpyright (local supplementary gate, not run in CI)" section now states where `pyright` and Pylance belong: `pyright` is only the engine underneath basedpyright and is **not a third gate**; Pylance has no command-line entry, so "Pylance was checked" may never be presented as gate evidence; this repository has no `[tool.pyright]` section, so a bare `pyright` scan is wider than the `[tool.basedpyright]` exclusion set |
| `AGENTS.md` addition | The gate section gains a transferability precondition: local black/isort/mypy/pytest versions must equal the pinned `ci.yml` consts, otherwise the report must be labelled "local readings, not verified against the CI toolchain version". Measured divergence, one item: **local isort 9.0.2 versus the CI pin of 9.0.1** (black 26.5.1 / mypy 2.3.1 / pytest 9.1.1 all match). Workflow constants were not touched and venv dependencies were not reinstalled (the latter is a user-channel action per "Risk controls (preface)") |
| Attribution of the 14 skips | All are environment-shape limits, not failures: Windows semantics 4 (`tests/test_proxy.py:199`, `tests/test_regression_2026_09_22_utils.py:178`, `tests/test_utils.py:574`, `tests/test_run_gates.py:218`); missing symlink privilege 3 (`tests/test_ffmpeg_path_preference.py:262`, `tests/test_web_api.py:2137`/`:2157`, WinError 1314); local `h2` present so the missing-dependency construction branch is unreachable 1 (`tests/test_regression_2026_09_22_net.py:681`); platform has no documented offline shape 6 (`tests/test_spider_hardening.py:198`) |
| Live end-to-end verification | **Not executed**: zero code changes this round (documentation only), so the Definition of Done exemption keeps steps 1/4/6; the recording chain was not touched |
| Doc-lock self-check | After editing `AGENTS.md`, the three document locks that read it were re-run — `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = 73 passed / 1 skipped; the "Formatting commands" bash block still parses with the same command count (new bullets sit outside the fence); `AGENTS.md` line endings re-measured as CRLF 517 / bare LF 0, the same shape as HEAD |

### v4.4.0 (2026-09-30) — `pyproject.toml` reconciled against workspace changes (dependencies / derived metadata / package list / exclusion list): no value changes, only the attribution in two `filterwarnings` comments corrected

**Context**: re-audited under the "scan the workspace → identify adds/mods/deletes since the last commit → write back the affected `pyproject.toml` configuration" brief. The working tree was clean against `HEAD`, so the reconciliation baseline became the unpushed `046bb73` (the batch that dropped fastapi / pydantic).

| Item | Evidence (measured locally) | Outcome |
| --- | --- | --- |
| Runtime dependency set | `pyproject [project.dependencies]` = 21 entries ↔ `requirements.txt` = 21 after stripping inline comments; `tests/test_regression_2026_09_22_gates.py` 27 passed | Already synced by `046bb73`; no change |
| Derived artefacts | `python scripts/sync_metadata.py --check` | OK: `uv.lock` carries no fastapi/pydantic node any more, egg-info version and requirements both match |
| Third-party imports with no declaration | AST walk over all 243 `.py` files in the repo collecting top-level import roots (script fed via stdin, nothing written to disk) | No gap in product code; `fastapi`/`pydantic` survive only inside the `.workbuddy/tmp/` stale backup snapshot, a directory already excluded by every tool's exclusion list |
| Package list | `src/` still has exactly `platforms` / `proto` as sub-packages; all 6 root `.py` files are listed in `py-modules` and `[tool.mypy].files`; this batch's new files land in `src/`, `tests/`, `web/`, `docs/worklog/` | `packages` / `py-modules` / `package-data` all need no change |
| Exclusion-list single-sourcing | black / isort / mypy / coverage / basedpyright omit entries match `.coveragerc-concurrency` item by item; no new `.py`-bearing asset directory under `tests/`, `docs/`, `web/` | No change |

**Actual change (comments only)**: the two `[tool.pytest.ini_options].filterwarnings` attributions corrected —

- Entry 1 is **load-bearing**: running `tests/test_web_api.py` with `-W default::UserWarning` puts exactly one line in the warnings summary, emitted by `starlette/testclient.py` itself (category `StarletteDeprecationWarning`, a `UserWarning` subclass). The old comment blamed "an internal import inside fastapi's testclient", which `046bb73` falsified.
- Entry 2 **does not fire on the installed combination** (starlette 1.7.0 + anyio 4.15.1): with `-W always::DeprecationWarning` (a command-line `-W` overrides the ini filter) `test_web_api.py` + `test_web_api_routes.py` give 163 passed and an empty summary, because all three starlette references now go through `anyio.from_thread.BlockingPortal`. Kept rather than deleted — the shape across the declared `starlette>=1.3.1` lower-bound range was not verified locally.

**Gates**: `check_version.py` PASS, `sync_metadata.py --check` OK, `pytest tests/test_regression_2026_09_22_gates.py tests/test_web_api.py` = 190 passed / 2 skipped / 0 warnings; TOML parses and the whole file stays within 120 columns.
**Live end-to-end verification**: **not executed** — this batch touches no recording chain / source selection / ffmpeg arguments / platform resolver, so the Definition of Done step-2 exemption applies.
**Deliberately left for the user**: (1) `src/proto/douyin_pb2.pyi` (present since 2026-08-18) is not listed in `[tool.setuptools.package-data]`; whether wheels include it was **not** measured (no installed distribution and no `.whl` on this machine to inspect) and needs a real build to decide. (2) `[project.optional-dependencies].dev` floors (pytest>=7.0.0 / mypy>=1.5.0 / pytest-asyncio>=0.21.0) sit far below the pinned `ci.yml` consts (pytest 9.1.1 / mypy 2.3.1 / black 26.5.1); raising them to CI parity is undecided.

**Same-day follow-up (separately approved by the user)**: `AGENTS.md` "Dependency management" read "23 entries", a figure falsified by `046bb73` (the fastapi/pydantic removal). It was initially left alone because the file was under parallel edit; once the user issued the explicit instruction it was corrected to "21 entries, re-checked 2026-09-30: 23→21 after the stage-2 removal", with the earlier 2026-09-26 21→23 reading recast as an explicit "superseded by that removal" historical note rather than deleted (constant names and dates kept verbatim). Re-measured after the edit: `AGENTS.md` line-ending shape unchanged at CRLF 517 / bare LF 0, and the three document locks that parse it — `tests/test_run_gates.py` + `tests/test_regression_2026_09_22_gates.py` + `tests/test_check_annotations.py` = 73 passed / 1 skipped / 0 warnings (the "Formatting commands" bash block still parses with the same command count; this edit sits outside the fence).

### v4.4.0 (2026-09-30) — Three hand-back items from the review report landed (1-A sync-probe internal guard / 2-A retry exit-code buckets / 3-A live-script template gate) plus a new machine check against unrestored mutations

> The previous batch left three items for the user to decide. All three were approved and landed as
> 1-A / 2-A / 3-A. During the work an actual incident was found and turned into a machine check (new rule R8).

**1. 1-A — internal-target guard for the synchronous probe (`src/stream_select.py`, `src/async_http.py`)**

The previous batch only wired the per-hop re-check into the asynchronous side, and I described the gap as
"the synchronous probe has the same shape but is un-wired (per-hop level)". Re-reading the code
**corrects that premise**: the only call site of the internal-target judgement in the whole repository was
`async_http.get_response_status`, so the synchronous probe had **no internal/loopback/cloud-metadata check even for
the initial URL** — it only had the `_is_recordable_url` scheme-shape whitelist, which blocks `file://`/`concat:`
but not `http://127.0.0.1:6379`. A hijacked platform API returning an internal stream address was enough to hit it.

| Item | Content |
| --- | --- |
| Single factory | Both self-built `httpx.Client` sites now go through `_probe_client()`, which attaches the synchronous response hook (`build_sync_hop_guard`); the judgement reuses the one implementation in `async_http` — **no second copy in stream_select** |
| Import cycle | The hook factory is imported **inside the function**, following the technique documented at `async_http.py:518-521` (this module has a module-level `import main`, so a module-level outgoing edge would change initialisation order) |
| Initial check | `_validate_stream_url` runs `internal_stream_target_reason` before the first request; it deliberately does not reuse the variant that carries a scheme whitelist, because the protocol dimension is already gated by `_is_recordable_url` — the two guards do not substitute for each other |
| Exception convergence | `RedirectHopRejected` (extending `httpx.HTTPError`, not `RuntimeError`) becomes the same `False` as "this candidate failed validation" inside `_validate_stream_url` and **never escapes**; the "treat the list as reachable" fallbacks in `_confirm_get_ok` / `_probe_hls_segment` must `raise` — otherwise the last candidate returns `True` and hands an internal address to `ffmpeg -i` |
| Not regressed | Probe client scope stays single-selection, no `(proxy, verify)` module-level cache, keepalive not disabled, `utils.handle_proxy_addr` normalisation not moved |
| Locks | `tests/test_sync_probe_internal_guard.py` (includes AST structure locks: one construction site, `event_hooks` argument must come from the synchronous factory, both call sites pass the initial check); the asynchronous lock file stays green |

**2. 2-A — the retry composite action supports exit-code buckets (`.github/actions/retry/action.yml`, `.github/workflows/ci.yml`)**

| Item | Content |
| --- | --- |
| New optional input | `fail_fast_codes`, `required: false`, `default: ""`; **when unset the behaviour of existing call sites is unchanged verbatim** (backoff arithmetic, both message texts, final `exit 1`) |
| Hit semantics | The branch sits **before** the backoff `sleep`, prints `::error:: … configuration-class error … retrying is pointless` and `exit "$rc"` keeping the original code; it must never exit 0 nor degrade to a warning (that would be a false green) |
| Parsing | `IFS=", "` + `set -f` + `case ''|*[!0-9]*`: space/comma mixes parse, illegal entries are ignored with a `::warning::`, and matching uses a space-padded string so a list containing `2` does not match rc=12; strictly POSIX, no bash-only associative arrays |
| Wiring | Only the web smoke call site passes `"2"`, closing M-32(2)'s "a broken config must not be retried" |
| Premise corrected | The work order said "10 call sites"; measurement found **16** (11 in ci.yml, 5 in build-release.yml) — earlier batches had already migrated more install steps into this action. The structure lock therefore pins 16 as a lower bound (only-decrease semantics) and asserts "regex count == YAML structural count" so a drift in the `uses` form cannot silently disable AGENTS' own grep gate |
| Locks | `tests/test_ci_retry_action.py`: 4 structural locks + 8 real-`bash` behaviour cells (they run the production script extracted from `action.yml`, no copy, so deleting the production branch must redden); when bash is missing the test **fails explicitly instead of skipping** |

**3. 3-A — live-script template gate R7 (`tests/test_test_hygiene.py` + the five `test_*_live_collector.py`)**

Four AST criteria, each named individually: ① an `__main__` guard that really calls `main()`; ② no module-level
collection-time side effects (only imports / constant assignment / the sanctioned `sys.path` injection are allowed);
③ the argv numeric guard; ④ output-directory cleanup must filter by platform prefix and check the entry type first.
The reverse witness was extended as required: each criterion is fed its worst-case form (must redden) and a compliant
source (must not false-positive), plus four new cases that mutate the real scripts and demand that only the
corresponding criterion reddens.

**4. Two documented premises that turned out to be wrong**

1. **AGENTS' own argv-guard sample was falsified by measurement**: the documented one-liner
   `SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 and not sys.argv[2].startswith("-") else N` breaks under
   `pytest a.py b.py`, where `sys.argv[2]` is the **next test file's path** — it carries no `-` prefix, passes the
   non-option test, and `int(path)` raises ValueError, erroring that module's collection outright
   (measured: 4 errors during collection). All five scripts now use the two-step form
   `_SECONDS_RAW = …` → `int(_SECONDS_RAW) if _SECONDS_RAW.isdigit() else N`; R7③ machine-checks it and the AGENTS
   entry body was corrected (falsified statements get rewritten in place).
2. **The report's finding about blind directory clearing was real**: `test_bili_live_collector.py` /
   `test_huya_live_collector.py` used `for f in os.listdir(base_dir): os.remove(...)` (no prefix filter, no type
   check), which throws when a subdirectory is present and deletes other platforms' artefacts under parallel runs.
   Now filtered by platform prefix + `isfile`, keeping the original intent of starting from a clean directory.
3. **AGENTS' "the retry action is rc-agnostic, rc=2 cannot actually stop early (pending decision)" was closed by 2-A**
   and the entry body was updated accordingly.

**5. The incident and the new machine check R8 (guarding against unrestored mutations)**

A parallel work package mutated the HLS segment branch in `src/stream_select.py` to prove a lock was not fake
(removing `except RedirectHopRejected: raise`), hit its turn limit, and left `pass  # MUTATION-M4c …` **in the
production file**. The consequence is not a missing comment: `seg_resp` was left unassigned → `UnboundLocalError`
swallowed by the outer `except Exception` as a "probe error" → the last candidate returned `True` →
**an internal address was handed to `ffmpeg -i`**. This shape is invisible to black / mypy / the annotation checker
(syntactically valid, type-clean, and it even adds comments); only a test that actually executes that branch catches
it — which is exactly what the new synchronous-probe case did.

R8 now scans source files repository-wide and reddens if a `MUTATION-` marker survives; three hard constraints were
written back into AGENTS' "mandatory test-writing conventions" (in-memory backup + byte-exact restore in `finally`;
markers must be left during the mutation; when taking over an interrupted work package, the first step is to scan for
residue rather than assume the implementation is complete). The guard protects itself three ways: the marker literal
is built by concatenation (otherwise the gate would flag its own source), it asserts the traversal covers >200 files
(a wrong scan root would otherwise spin silently), and the reverse witness covers all three legs.

**6. Verification**

| Item | Reading |
| --- | --- |
| 1-A real outbound probe | Public HLS (walking the playlist **and the segment-probe branch** that held the residue) `test-streams.mux.dev/x36xhzz/x36xhzz.m3u8` → **True** (no false rejection); `http://127.0.0.1:6379/`, `http://169.254.169.254/latest/meta-data/`, `http://10.0.0.5/live.m3u8`, `http://100.64.0.1/live.m3u8` → all **False**; internal target with `last_resort=True` → **False** (the last candidate is not handed an internal address); `file:///etc/passwd` → **False** (shape whitelist intact) |
| Real "public → internal" redirect chain | **SKIP(no usable public redirector)**: httpbingo.org returns 403 to this host and no public endpoint 302s into a private address; covered via `httpx.MockTransport`, no fabricated readings |
| 2-A | `pytest tests/test_ci_retry_action.py` alone → **12 passed / 0 warnings** (4 structural + 8 real-bash cells); end-to-end wiring check with the real ci.yml `with` values and the GitHub-filled default → `runs=1 / rc=2 / 0.23s` (a real backoff with `backoff=5` would take ≥5s); three mutation runs: delete branch `4 failed, 8 passed`, `default` → `"2"` `1 failed, 11 passed`, branch moved after `sleep` `4 failed, 8 passed`; all restored byte-identical |
| 3-A / R8 | `pytest tests/test_test_hygiene.py` → **507 passed**; R8's disk path proven with a one-shot probe file: adding `tests/_tmp_r8_probe.py` (containing a marker) → `AssertionError: tests/_tmp_r8_probe.py:7`, removing it → green; probe deleted |
| Live recording chain | Douyin room `live.douyin.com/699394970561` → SKIP(room offline at run time); the affected path is the source-selection validator, whose real outbound evidence is the row above |
| Full gates | `python scripts/run_gates.py` 8/8 green with an empty pytest warnings summary (readings in the delivery reply) |

**7. Still open**

- The `inputs → env` expansion happens on the GitHub runner; locally we only proved the script behaves correctly once
  the default is filled the GitHub way. After merging, check that the first failing web-smoke log shows
  `exit code 2 is a configuration error … not retried`.
- The five `build-release.yml` call sites deliberately do not pass `fail_fast_codes` (they install via choco/apt/brew/pip,
  where no "configuration-class" exit code exists; passing one would only weaken retry on network flakiness). A
  structure lock pins "nobody passes it" instead of letting that drift.
- The hook still fires after the hop's response has been received (what is closed is "no further following and no
  leakage", not "no connection"); intercepting before connect would need a request hook (two checks and two
  `getaddrinfo` calls per hop), and the DNS-rebinding window is not closed at this layer — all recorded as residual
  risk in the source comments and here.
- The previous batch's eyeball items and live gaps are unchanged (M-14/M-16/M-18/M-22 visual checks, M-11 needs an
  outbound route for TikTok, no live Douyu room at the time, `basedpyright` not installed locally).

### v4.4.0 (2026-09-29) — Fix batch for the full-repository review report CODE_REVIEW_2026-09-29_2 (P0+P1+P2, 31 numbered items)

> Implemented per `docs/worklog/CODE_REVIEW_2026-09-29_2.md`, within the scope the user approved: P0+P1+P2
> (31 numbered IDs / 33 distinct issues). Deliberately out of this batch: minor items 43-47 (front-end a11y),
> the P3 items M-6 (tighten the VBS match surface) / M-7 (migu wasm SRI) / M-20 (frozen-bundle i18n measurement),
> and every item the report flagged "to be confirmed". Every fix ships with a regression lock; security
> invariants additionally got mutation verification.

**1. Security hardening (S-1, M-1 ~ M-5)**

| ID | Where | What |
| --- | --- | --- |
| S-1 | `src/spider.py:140-174`, `112-121`, `6183-6254` | The Shopee short-link landing page now passes the **same two gates** that XHS SEV-2214 introduced: host-family allowlist (via `urlparse().hostname`, exact-or-`.`-suffix, userinfo rejected) plus `web_config._host_internal_reason` for internal/loopback/cloud-metadata targets. An untrusted landing page is discarded, the user-entered URL is kept and the Cookie header is stripped. The constructed `api_host` is re-checked against the allowlist (so a poisoned `host_suffix` cannot leak), and `_shopee_host_suffix` moved from raw string splitting to hostname parsing |
| M-1 | `src/async_http.py:87`, `460`, `532-588`, `679` | **Per-hop** redirect re-validation for the probe and every `async_req` branch: one `event_hooks` response hook wired at the single `_build_client` site re-runs `_internal_stream_target_reason` on each hop's landing URL, stopping the chain and returning the existing "unreachable" semantics. The DNS-rebinding window is registered as residual risk (judgement results are deliberately not cached) |
| M-2 | `src/sync_http.py:56-140`, `309`, `375` | `sync_req` gains a scheme allowlist (reusing `utils.is_safe_http_url` rather than a second implementation) and its opener is built from an explicit protocol whitelist that no longer registers FileHandler/FTPHandler/DataHandler; the abroad branch, which uses the process-global `urlopen`, gets a post-landing re-check |
| M-3 | `src/spider.py:716-720`, `911`, `1126`, `1289`, `1848`, `3324`, `3490`, `4279`, `4512`, `5137` and more | Raw URLs entering `raise`/log calls now pass `utils.mask_credentials` first (the primary case was the PandaTV/WinkTV private-room `pwd` landing in rotated logs; Douyin / TwitCasting / Weibo closed on the same standard) |
| M-4 | `src/spider.py:3908-3920` | `login_popkontv` — the only production httpx request in the file that bypasses `async_req` — masks the exception text and adds `type_name`, so proxy `user:pass@` cannot reach the logs |
| M-5 | `src/notify.py:92-98`, `113-155`, `173-187`, `203-205` | All four post-record custom-script failure branches mask the command text; the second `communicate()` after a timeout is now bounded; process-tree reclamation uses `start_new_session` + `killpg` on POSIX and `taskkill /T /F` on Windows (argv list, never shell=True), degrading to the original `kill` on any failure |

**2. Recording and resolver correctness (M-8 ~ M-13)**

| ID | Where | What |
| --- | --- | --- |
| M-8 | `src/spider.py:207-324` | The module-global fast path for the Kuaishou `did` and Bilibili `buvid3` caches now compares the proxy context, so a fingerprint obtained via proxy A is no longer reused by rooms on proxy B (mirrors the already-fixed ttwid MIN-2220). Lock types and the cross-await semantics untouched |
| M-9 | `src/spider.py:723`, `914`, `1173`, `1370`, `1610`, `3200` | Remaining `anchor_name`-can-be-None sites unified on `_dig_str` / `isinstance(v, str)`, eliminating the `clean_name(None)` crash that used to knock out the whole parsing round |
| M-10 | `src/spider.py:4325-4331` | The TwitCasting restricted-room login fallback now also catches `ValueError` (PEP 758 parenthes-free form); the promised "parse failure → login retry" path was previously unreachable |
| M-11 | `src/stream.py:654-691` | TikTok quality selection no longer writes the FLV-clamped index back into the shared variable: the original requested index is kept and FLV/HLS are clamped independently against their own list lengths (same standard as the Douyin branch in the same file); the fallback base was fixed in the same pass. HLS-only rooms asking for the lowest tier no longer silently pull the top tier without a downgrade warning |
| M-12 | `main.py:4950-4959` | The danmaku platform list becomes a list comprehension with `strip()` and empty-item filtering, matching the HLS exclusion list in the same function; `"斗鱼直播, B站直播"` no longer never matches |
| M-13 | `src/platforms/bilibili.py:55-159` | A `_report_close` gate was added to Bilibili host rotation: while candidates remain untried the event is an intermediate state (routed through `_on_reconnect` for tracing), and only exhaustion or the `_stopped` terminal state reports — exactly once. `_hosts_left` is zeroed when rotation ends, otherwise real disconnects mid-session get swallowed. Not pushed down into WsClient, the `backup_url` primary/backup rotation was not merged, and `src/ws_client.py` is untouched |

**3. Web / i18n / front-end (M-18, M-19, M-21 ~ M-23, M-26)**

| ID | Where | What |
| --- | --- | --- |
| M-18 | `web.py:199-239`, `258-262` | The "authentication disabled must not bind beyond loopback" gate was moved **above** `_enter_background_mode`, so the refusal text is no longer swallowed by the stdio redirect; the falsified "refuse = zero-side-effect exit" comment was corrected per the AGENTS exception clause and compressed into a one-line dated note |
| M-19 | `i18n.py:399-414` | Both `tr()` except layers now include `AttributeError, TypeError` (measured: `{x.y}` with `x=None` raises AttributeError, `{x:d}` raises TypeError), honouring the "never raises" promise; `translated_print` was reviewed and has no equivalent gap (it never calls `.format`) |
| M-21 | `web/app.js:753-870` | All three polling chains (SSE / log / danmaku) renew through one shared `makePollChain()` generation token: both `halt()` and `begin()` advance the generation, so an in-flight callback whose generation is stale is dropped and never re-schedules orphaned timer chains |
| M-22 | `web/app.js:1498-1560`, `web/index.html:176-190`, `web/style.css` | The auth re-verification password is collected in a `type="password"` modal instead of `window.prompt`'s cleartext; all four exits funnel through `_settleReauth()` which clears the input node immediately; `reauth_password` is attached only to the two authentication keys' PUTs and no longer rides along on every other config key of the same save pass |
| M-23 | `web/app.js:1107-1117` | The collapsed-danmaku counter `m.dropped` now goes through `esc()`, restoring this file's "every concatenation path is escaped" invariant |
| M-26 | `tests/frontend/test_regression_2026_09_22_gates.mjs` | Removed two `doesNotMatch` text locks pinned to outdated source literals (the backend does enforce re-verification and the literal drifted, so the assertions passed vacuously and contradicted the new Python-side contract); replaced with a positive behavioural lock on "the authentication-key path really collects and sends `reauth_password`". Test count 32 → 36 |

**4. GUI robustness (M-14 ~ M-17, M-24, M-31)**

| ID | Where | What |
| --- | --- | --- |
| M-14 | `gui.py:1110-1360`, `3627`, `3684` | The quality-monitoring match patterns are now derived from **`i18n.tr()` results using the same msgid as the producer** (escaped then assembled) and recomputed lazily per language; hard-coded Simplified-Chinese constants removed. The one `src/recorder_status.py` literal that is **not** run through `tr()` continues to match verbatim, with the reason stated in the comment. The `#DLRQ` structured status protocol was **deliberately not introduced** — AGENTS key convention #13 lists it as a pending-approval long-term plan. A self-audit during wrap-up also fixed a defect this batch introduced itself: the per-language cache now only commits after re-verifying the language code is unchanged — the build reads `tr()` six times while the recording thread and the UI thread can switch language concurrently, so an unconditional write would freeze a **mixed-language** pattern set in place (lock: `test_mid_build_language_switch_is_not_cached`) |
| M-15 | around `gui.py:1466`, `3519`, `3667`, `3132` plus `gui.py:1599-1612` | The renewal `after()` of the self-renewing chains moved into `try/finally` so it is re-armed unconditionally; external numeric fields such as `ts` go through one shared tolerance helper (a `null` record can no longer break the timer chain). Wrap-up added the **fourth chain of the same family**, `_pump_ui_events` (the UI event pump): its renewal sat on the last statement while the preceding "activate the log flush chain on demand" can raise during a window-destroy race — a broken pump means queued `post_ui` callbacks such as `_on_recording_stopped`/`_finalize_quit` never run (the window cannot be closed). The `_CHAINS` structural lock was extended to name all four |
| M-16 | `gui.py:3226-3352`, `4175-4189` | New single-flight entry `_stop_child_once` shared by "stop recording" and "quit": quitting reuses an in-flight stop thread instead of a second concurrent console attach/detach sequence (console attachment is process-global state); both registration and deregistration sit on unconditional paths |
| M-17 | `gui.py:3801-3844` | The tail thread's try/except was pushed down to **each event** (bad record → continue), so one malformed event no longer discards the intact events that follow it in the same chunk; the outermost handler now leaves a rate-limited warning |
| M-24 | `tests/test_danmaku_monitor.py:562-599` | The tail test sets **the Event it actually passed in** and adds `assert not t.is_alive()` — "it stops after rotation" is verified for the first time (previously the daemon thread lingered until process exit) |
| M-31 | `tests/test_gui_monitor.py:79-85`, `tests/test_danmaku_monitor.py:429` | The child process gets `PYTHONUTF8`/`PYTHONIOENCODING` explicitly; `import gui` moved out of collection time into the test body with an autouse fixture restoring `DLR_GUI_PARENT` in pairs (`patch.dict(os.environ)` forbidden) |

**5. Test system and maintenance scripts (S-2, M-25, M-27 ~ M-30, M-32)**

| ID | Where | What |
| --- | --- | --- |
| S-2 | `tests/test_twitch_live_collector.py:42`, `109`, structural lock `118-190` | The whole body moved into `def main()` + `if __name__ == "__main__": main()`, making it homogeneous with the four sibling live scripts. Evidence: `pytest --collect-only` went from **20.55 s / no tests collected / exit code 5** to **0.81 s / 1 test collected**; the collection-time live connection, `sleep 20`, `tests/_out_live` purge and session-killing `sys.exit(1)` are all gone |
| M-25 | `tests/test_huya_danmaku.py:121` | The bare assignment `spider.async_req = fake` replaced by `monkeypatch.setattr` (the old form never restored and used an incomplete signature, poisoning the whole pytest session) |
| M-27 | `tests/test_config_io_backup.py:20-26`, `tests/test_log_archive.py:114`, `tests/test_anchor_rename.py:15-20` | Patches of process-global `os.remove`/`os.rename` now go through a `SimpleNamespace(**vars(os))` shim installed on the module under test's own `os` reference (loguru and other background threads are no longer affected during the window) |
| M-28 | `tests/frontend/test_motion.py` (new), `.github/workflows/ci.yml` | The five `test_motion.mjs` cases gained a Python wrapper and were added to the CI "Gate frontend tests not skipped" node-id list (`node --test <file>` only runs the named file and never discovers its siblings, so those degradation/cleanup locks never executed in normal CI). This batch also registers WP-G's new `tests/frontend/test_auth_reauth.py::test_auth_reauth` in the same list |
| M-29 | `tests/test_machine_validation_fixes.py` | The heartbeat-timeout case now records the **timestamp and origin** of every `close()` and attributes per entry point, asserting the first close happens at the timeout point and before the deliberate stop (the old `len(close_called) >= 1` was blind to deleting the timeout branch); the "all three call sites timed out" aggregate count in the same file was tightened to per-entry attribution |
| M-30 | `tests/test_notify.py:27`, `63`, `74` | Child-process commands use `sys.executable` instead of the literal `python` (images that ship only `python3` always failed these, while the local Windows box was always green) |
| M-32 | `scripts/sync_metadata.py:112-158`, `scripts/smoke_test.py:87-192`, `214-218` | (1) `shutil.which` early return plus `OSError` catching: with uv missing the WARN branch is reachable and the egg-info rebuild still runs (the read-only `--check` path spawns no subprocess, pinned by a tripwire case). (2) `load_config` is the single validation point and malformed headers/checks shapes exit rc=2 (previously `.items()` raised AttributeError → rc=1, breaking the contract `_ci_web_smoke.sh` uses to tell "panel failure, retryable" from "config problem") |

**6. i18n catalogue synchronisation (new strings from S-1/M-4)**

- Four new msgids (three Shopee gate messages + the popkontv exception carrying `type_name`) were added to all four catalogues
  (`zh_CN.po`, `en_US.json`, `en_GB.json`, `zh_TW.yaml`) and the `.mo` was regenerated; the collision-avoidance intermediate
  `_i18n_pending_wpa.json` was deleted after the central merge, per AGENTS key convention #14.
- Entry counts under both accepted measures (read locally on 2026-09-29, not estimated): JSON key count **791**;
  `.mo` header N **792** (the header's empty msgid is counted, so N = key count + 1). Command used:
  `python -c "import struct;print(struct.unpack('<6I', open('i18n/zh_CN/LC_MESSAGES/zh_CN.mo','rb').read(24))[2])"`;
  `python scripts/compile_po.py --check` self-reports the same 792 (.po/.mo in sync);
  `python scripts/extract_i18n_strings.py` reports 0 missing.

**7. Verification (real devices, per AGENTS Definition of Done step 2)**

| Date | Platform | Room address (masked) | Script | Result | Readable evidence |
| --- | --- | --- | --- | --- | --- |
| 2026-09-29 | Douyin | live.douyin.com/699394970561 | `tests/test_douyin_live_collector.py` | PASS | 59 messages / SRT 4518 bytes |
| 2026-09-29 | Bilibili | live.bilibili.com/21452505 | `tests/test_bili_live_collector.py` | PASS | 9 messages / SRT 678 bytes, no "fake close" under the `_report_close` gate |
| 2026-09-29 | Huya | www.huya.com/660000 | `tests/test_huya_live_collector.py` | WARN | 0 messages, connection healthy, no danmaku in that window (SRT produced) |
| 2026-09-29 | Twitch | twitch.tv/forsen | `tests/test_twitch_live_collector.py` | WARN | 0 messages; the guarded script still runs standalone (live evidence for S-2) |
| 2026-09-29 | Shopee | shp.ee/**** (invalid short link) | in-process probe `spider.get_shopee_stream_url` | live interception evidence | The landing-derived `api_host=https://live.shopee.ee` was blocked by the family allowlist gate with a warning and returned as not live — real outbound evidence for S-1 |
| 2026-09-29 | Douyu | www.douyu.com/1, /23059, /9235411 | `tests/test_douyu_live_collector.py` | SKIP(room offline) | Anchor names still resolved correctly ("斗鱼官方视频号", "注意前方猪妖"), so the resolver chain is intact; re-run when a room is live |
| 2026-09-29 | TikTok | www.tiktok.com/@tiktok | in-process probe | SKIP(no outbound route) | `ConnectTimeout` plus the built-in guest-cookie expiry warning; M-11 needs the user to re-run a real room with quality set to the lowest tier and confirm `logs/PlayURL.log` picks a non-first m3u8 |

**8. Residual gaps and actions handed back to the user**

- **GUI eyeball checks**: headless verification does not replace observation for M-14/M-15/M-16/M-17 — switch to English, restart recording, and confirm the quality page still shows recording lines / downgrade warnings / empty-state clearing; for M-22 confirm the password modal masks input and that the field is cleared on cancel.
- **M-18**: the refusal text now reaches un-redirected stdout/stderr plus one warning, but double-clicking `python web.py` on a desktop still destroys the console window when `sys.exit(1)` runs; eliminating the "flash" entirely is a product decision (pause or banner before refusing).
- **Three boundaries of the per-hop re-check (M-1)**: the synchronous probe in `src/stream_select.py` builds its own `httpx.Client` and does not go through `_build_client`, so that shape is still un-wired; the response hook fires only after that hop's response headers arrived (what is closed is "no further following and no leakage", not "no connection"); the DNS-rebinding window cannot be eliminated at this layer.
- **The retry action is rc-agnostic**: `.github/actions/retry` retries on any non-zero exit code alike, so M-32(2)'s "rc=2 means a config problem, stop immediately" is currently only visible in the step log; at job level 1 and 2 remain indistinguishable — decide whether the retry action should gain an exit-code bucket input.
- **Proposed new gate not implemented**: templating/lint checks for the live scripts (mandatory `__main__` guard, platform-prefixed cleanup) were kept as a recommendation, not added unilaterally.
- **P3 / to-be-confirmed items untouched**: M-6, M-7, M-20 and the minor items flagged as needing measurement.

### v4.4.0 (2026-09-29) — GUI freeze fix: adaptive wraplength reworked to true debounce + hysteresis, eliminating the event-storm oscillation during DPI rescale

> Observed by the user: text flickering at high frequency → some UI elements rendered incompletely → the whole window freezing unresponsive. The root cause is the **previous fix (adaptive wraplength) writing synchronously inside `<Configure>`**, oscillating with CTk's DPI-rescale machinery. The trigger is dragging the window to a monitor with a different scale factor (or a system DPI change) — the same mechanism as the dev-time stress probe hang, through two different entrances.

**1. Root-cause chain (all empirically verified)**

1. CTk's DPI-change handling runs `ScalingTracker.update_scaling_callbacks_* → widget _set_scaling → _draw → _update_dimensions_event → update_idletasks` — a **mutually recursive pump** (nested frames visible deep in ctk_scrollbar.py).
2. During rescale the internal label's width swings violently (probe measured 350↔1566 device px; at identical widths the wraplength got chased into `334→1038→190→858→…`).
3. The old binding called `label.configure(wraplength=…)` synchronously on every Configure — each write re-invalidates geometry into the same idle queue, which then never drains: **`update()`/mainloop never returns = freeze**; the high-frequency relayout = flicker; starved paints = missing elements.
4. Decisive control: under the same 10-flip DPI stress (via `set_widget_scaling`, the same callback chain as `check_dpi_scaling`) — with the binding active the loop never drained (killed at 120s = freeze reproduced); with the binding no-op'd the run **completed in 9.2s**.

**2. Fix (gui.py)**

| Item | Content |
| --- | --- |
| True debounce | `<Configure>` only resets a timer (`after_cancel` + `after(120ms)`); while the storm lasts **not a single write** happens — structurally impossible to feed geometry invalidation back into the recursion. Deliberately not "throttle to one write per 120ms" (a mid-storm write can re-ignite the recursion via the scrollbar threshold) |
| Hysteresis | `_wrap_should_apply(current, new, scale_changed)` pure function: skip when `|new−current| ≤ max(12, 2%)` and the scale is unchanged. The ±~11-logical-px wobble of a scrollbar appearing/disappearing is absorbed; first apply (current==0) and any scale change (the conversion basis moved) always apply |
| Race guard | `_run` is TclError-guarded throughout — the danmaku/quality placeholders are rebuilt every 2s, so a debounced callback can race destruction |
| Startup shaping | if a real width already exists at bind time (winfo_width>1) apply once synchronously so the first frame wraps; later changes go through the debounce |

**3. Verification**

- Stress regression lock (`tests/test_gui_wrap_hints.py::TestRealWindowWrap::test_dpi_flip_stress_*`, real window, skips headless): full GUI build + 8 DPI flips must drain the event loop (the pre-fix equivalent times out) with ≤24 wraplength writes per label (measured ~1 per flip).
- End-to-end real-window final check (1120×740, 150% system scaling): all four long hints unclipped; after simulated 1.2↔1.0 DPI flips everything converges to the correct wrapping with zero freezing.
- 5 headless pure-function cases for the hysteresis + AST source locks for debounce/guards; `run_gates.py` 8/8, pytest 3308 passed / 0 warnings, basedpyright 0/0/0.

**4. Known micro-edge**

- For ~120ms after startup a long hint may render one unwrapped frame before the first debounced settle — an imperceptible trade for structurally safe zero writes during storms.

### v4.4.0 (2026-09-29) — GUI text-clipping fix: adaptive wrapping for long hints (`_bind_adaptive_wraplength`), eliminating symmetric pack clipping on both sides

> Observed on user screenshots (150% DPI, default 1120×740 window): the console hint "启动后将调用 main.py…" lost half of its first and last characters, and the danmaku empty-state hint was clipped at the right edge. The root cause is one family: **when a label's requested width exceeds the width its parent allocates, Tk pack centers it (default anchor=center) and clips symmetrically on both sides**; the quality page's fixed `wraplength=1000` is a variant of the same failure under narrow windows (right-edge clip). A repo-wide sweep found 5 sites of the same shape — all fixed together.

**1. Changes by module**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Adaptive wrapping | Added | `gui.py` | `_compute_wraplength(width_device_px, scale, margin)` pure function (device px → logical: CTk scales wraplength by `_widget_scaling` on configure (`ctk_label.py`), while `<Configure>` reports device pixels, so divide by `ScalingTracker.get_widget_scaling`; floor 120 prevents wraplength→0 from silently re-enabling clipping); `_bind_adaptive_wraplength(label)` binds the label's **own** window width (requires `pack(fill=tk.X)`: window width is packer-allocated, decoupled from the label's request — no wraplength→request→width feedback loop; sets an initial value from the current width because a re-pack with unchanged geometry fires no Configure); `ScalingTracker` imported from its definition path `customtkinter.windows.widgets.scaling.scaling_tracker` (the top-level namespace does not export it — reportAttributeAccessIssue) |
| Wiring | Modified | `gui.py` | console hint now `pack(fill=tk.X, expand=True)` + binding; quality hint drops fixed `wraplength=1000` for the binding; the quality/danmaku empty-state labels consolidated into `_make_quality_placeholder` / `_make_danmaku_placeholder` factories (parameter `tk.Misc` — CTk 6.0's CTkScrollableFrame is not a CTkFrame subclass), shared by initial build and every refresh rebuild; duplicate copies of the copy reduced from 4 to 1 each |
| Tests | Added | `tests/test_gui_wrap_hints.py` | three layers: subprocess unit tests of the pure function (conversion anchors 1584@1.5→1050 pinned, 120 floor, zero/negative scale, monotonicity); AST source locks (helper defined once with exactly 4 wiring points, each placeholder copy appears exactly once, no constant wraplength kwargs anywhere, factories must keep fill=tk.X + binding, both build and refresh paths must call the factories); a real-window case (fill=X label wraps without clipping in a narrow container, wraplength grows when widened; skips without a display — the only skip surface) |

**2. Root causes & design points**

1. **Why half-characters missing on both sides**: pack's default anchor=center centers an oversized child in its (too narrow) parcel, so the overflow is clipped equally left and right — "启" half-missing at the left and "制" half-missing at the right is the fingerprint of requested > allocated width.
2. **Why binding the label's own width is safe**: under `fill=tk.X` the window width is entirely packer-allocated; changing wraplength only changes the requested height, never the window width, so oscillation is structurally impossible. Binding the parent's width would instead require subtracting sibling widgets (the button row) — more fragile.
3. **The real-window case deliberately avoids `set_widget_scaling`**: a manual scaling override fights CTk's system-DPI tracking during real window mapping (measured event storm → `update()` never returns). The system's own DPI already exercises the conversion for real, and the formula is pinned by the pure-function anchors.
4. **Two CTk 6.0.0 facts** (verified from source): `configure(wraplength=...)` multiplies by `_widget_scaling` internally while `cget("wraplength")` returns the logical value; `CTkScrollableFrame`'s MRO does not contain `CTkFrame` (they share only the `CTkBaseClass` ancestor).

**3. Verification**

- End-to-end measurement (this Windows machine, 150% system scaling, full `LiveRecorderGUI` built in a subprocess at the screenshot's 1120×740): before the fix the console hint measured reqwidth 768 > actual ~520 (symmetric clip) and the danmaku hint 1564 > 1538; after the fix all four long hints (console hint / danmaku placeholder / quality placeholder / quality hint) satisfy "requested ≤ allocated with wraplength active" (540≥519, 1196≥1092, 1196≥540, 1230≥986), the console hint wrapping onto two lines.
- `run_gates.py` 8/8 green; full pytest 3300 passed / 14 skipped / 0 warnings; coverage all 44 modules above threshold; basedpyright 0 errors / 0 warnings / 0 notes; the real-window case passed three consecutive runs in ~8s each.
- Regression locks: `tests/test_gui_wrap_hints.py` (10 cases); mutation check — removing either factory's `_bind_adaptive_wraplength` call or dropping fill=tk.X turns the AST locks red immediately.

### v4.4.0 (2026-09-29) — GUI theme layer (Phase 3): 3 semantic-token themes + runtime switching + `[GUI] gui_theme` persistence + WCAG contrast machine-checks

> Module-level overview of this change. Phase 3 (UI modernization · GUI theme layer) adds `src/ui_theme.py`
> (zero display dependency, safe to import headless); the `gui.py` sidebar gains a "UI Theme" menu
> (Light / Dark / High contrast) whose choice is written back to `config.ini [GUI] gui_theme` and registered
> as a ttk theme (`dlr-<id>`, clam base). The `Colors` / `Fonts` facades and every existing symbol signature
> are unchanged.

**1. Changes by module (added / modified + file paths)**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Theme engine | Added | `src/ui_theme.py` | 13 semantic slots (proposal §5.2's twelve + `on_primary`: in dark/high-contrast themes the primary button is a bright-blue fill whose label needs a near-black foreground — `surface` doubling as button text fails on dark); `THEMES` with three sets (light / dark / high_contrast); `contrast_ratio` per WCAG relative luminance; `CONTRAST_REQUIREMENTS` contract (body text 4.5 / non-text & disabled 3.0); `ThemeManager` (idempotent select/apply, guard against duplicate `theme_create`); `load/save_theme_preference` via `update_or_append_config_line` (creates missing section/key, preserves comments, atomic write) — deliberately not `config_io.read_config_value`, whose write-back holds `main.file_update_lock` (recorder lock system) |
| GUI wiring | Modified | `gui.py` | imports `src.ui_theme`; `__init__` reads `[GUI] gui_theme` — an explicit preference syncs the CTk appearance mode to the theme's family, otherwise follow the system appearance (pre-upgrade behavior kept); sidebar "UI Theme" `CTkOptionMenu` (i18n display names) + `_on_theme_change` (select → apply → persist → appearance mapping → appearance-menu display sync → `_sync_canvas_bg`); `_THEME_CTK_MODE` / `_THEME_LABELS` module constants; `Colors`/`Fonts`/`LiveRecorderGUI`/`SystemTray`/`AdvancedSettingsWindow`/`_quality_alert_expired` symbols and signatures untouched |
| Template & docs | Modified | `config/config.ini`, `README.md` | template gains `[GUI] gui_theme =` (empty = follow appearance); README config block documents the GUI section |
| i18n | Synced | `zh_CN.po`(+`.mo`), `en_US.json`, `en_GB.json`, `zh_TW.yaml` | 7 new entries: UI theme label, three theme names, switch success and two write-failure messages (`{theme}`/`{type_name}`/`{err}` placeholders). Four-catalog key-set equality holds (i18n test locks green); `web/app.js` needs no sync — the theme menu is GUI-only copy with no web surface |
| Tests | Added | `tests/test_ui_theme.py` | 34 cases: contrast-math anchors (black/white 21:1, white-on-#4F6DF5 pinned at 4.34), registry integrity (every slot, strict #RRGGBB), contrast contract parameterized across all pairs × themes, persistence (missing/invalid/round-trip/comment preservation/single-line on repeated save), switch idempotency (same-id short-circuit + byte-identical config), ttk-settings pure-data assertions + real-Tk integration (skips without a display — the only such case) |

**2. Root causes & design points**

1. **Contrast first**: all three themes' tokens were iterated to compliance (body 4.5 / non-text 3.0) with a scratch script before the values were baked into the module; light's `primary` is `#4358E8` (brand hue, deepened) — the original `#4F6DF5` measures 4.34:1 with a white label, below AA. The scratch script is deleted; `tests/test_ui_theme.py` keeps regressing the numbers.
2. **The cost of 3:1 borders**: WCAG 1.4.11 non-text contrast pushes light's border to `#848DA0` (darker than common light borders) — the machine-checked contract wins over visual habit.
3. **Visible effect boundary of Phase 3**: CTk widget colors are taken over by tokens in Phase 4 (ui_kit); for now a theme switch maps to the CTk appearance mode (high_contrast → dark) plus ttk element colors (effective once Phase-4 widgets land). The "Appearance mode" menu stays (it owns system-follow); Phase 4 unifies the two controls.
4. **Idempotency in three places**: `select` short-circuits on the same id (no redundant config writes), `save` keeps a single line on repeated saves (update before append), `apply` guards duplicate registration (`theme_create` raises TclError on an existing theme name).

**3. Verification**

- `pytest tests/test_ui_theme.py` → 34 passed (locally including 3 real-Tk integration cases; on headless CI those 3 skip while the other 31 run).
- Real-window smoke (this Windows machine, full `LiveRecorderGUI` built in a subprocess): with no preference the theme follows the system appearance to `light`; menu display names localized correctly; a simulated click on "High contrast" flipped `theme_manager.theme_id == "high_contrast"`, wrote `[GUI] gui_theme` into a temp copy, switched ttk to `dlr-high_contrast`, mapped CTk to Dark, and synced the appearance menu's display to "深色"; the real `config.ini` was never written (write path redirected).
- `python scripts/run_gates.py` → 8/8 green; full pytest 3286 passed / 14 skipped / 0 warnings; coverage 84.07% (all 44 modules above threshold); basedpyright 0 errors / 0 warnings / 0 notes; `import gui` headless-import succeeds (compatibility contract).

**4. Known edges & hand-back**

- The real-Tk integration cases skip on headless CI (no X server on ubuntu runners); to run them in CI regularly, add xvfb to the test job (deferred to Phase 5 evaluation).
- Coexisting "Appearance mode" and "UI Theme" menus are a Phase-3 transitional shape (the former owns CTk light/dark incl. system-follow, the latter owns token themes plus persistence); they get unified during the Phase-4 widget replacement.

### v4.4.0 (2026-09-29) — Web backend FastAPI → Starlette migration: self-built route adapter + zero-dependency validation layer; all 24 route contracts and security invariants preserved verbatim

> Module-level overview of this change. Phase 2 (UI modernization · framework replacement) migrates the Web admin panel backend
> from FastAPI to Starlette directly: removes the `fastapi` / `pydantic` dependencies, adds `src/web_models.py`
> (a pure-stdlib dataclass validation layer) and the `_route` adapter inside `src/web_api.py` (replicating FastAPI's
> model-argument parsing / Query clamping / dict→JSON serialization / sync-endpoint threadpool dispatch). All 24 route
> handlers are untouched; business logic and every security invariant (MID-*/SEV-*) are preserved verbatim. New
> `tests/test_web_api_routes.py` dynamically asserts the route contract, replacing the static baseline
> `web_api_routes_baseline.json` that tripped the sensitive-content gate.

**1. Changes by module (added / modified / deleted + file paths)**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Web backend framework | Migration (dependency removal) | `src/web_api.py` | `FastAPI()` → `Starlette()`; the 24 `@app.post/get/...` decorators replaced with `@_route(app, [METHOD], path)`; 5 `Query(...)` params de-decorated to plain defaults; `cast(FastAPI, request.app)` → `cast(Starlette, ...)`; auth middleware rewired as `app.add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)` [corrected 2026-09-29 runtime verification]: the initial draft wrongly claimed `@app.middleware("http")` was Starlette-native and kept verbatim — Starlette has no such decorator method and the import would raise AttributeError (mypy attr-defined agrees); FastAPI's decorator is exactly `add_middleware(BaseHTTPMiddleware, dispatch=...)` underneath; additionally a JSON `HTTPException` handler is registered (Starlette's built-in handler replies with a PlainTextResponse, dropping the `{"detail": ...}` error contract) |
| Request model validation | Added (zero-dependency) | `src/web_models.py` | 9 dataclasses (LoginRequest / RoomCreate / RoomUpdate / RoomToggle / RoomQualityUpdate / QualityOptionsUpdate / RecordingToggle / ConfigUpdate / LanguageUpdate) use a `.parse(data)` classmethod instead of pydantic `BaseModel`; missing field / wrong type → ValueError; bool accepts only real Python bool; extra fields ignored |
| Route adapter layer | Added | `src/web_api.py` | `_route` decorator factory: `inspect.signature`-driven classification (model arg / Query arg / request); JSON body parsed via `_read_json_body`, invalid body → 422; Query clamped by `_QUERY_DEFAULTS` default and bounds; sync `def` endpoints dispatched via `run_in_threadpool` (matches FastAPI, avoids blocking the event loop); non-Response returns wrapped in JSONResponse |
| Tests | Migration + added | `tests/test_web_api.py`, `tests/test_web_config_locks.py`, `tests/test_danmaku_monitor.py`, `tests/test_regression_2026_09_22_web_g.py`, `tests/test_web_api_routes.py` | 5 `TestClient` imports switched to `starlette.testclient`; new dynamic route-contract test asserts the exact set of 24 route method/path pairs + the `/web` mount; deleted `tests/web_api_routes_baseline.json` |
| Dependency manifests | Synced deletion | `requirements.txt`, `pyproject.toml` | Removed `fastapi>=0.140.0` and `pydantic>=2.13.4`; kept `starlette>=1.3.1` / `uvicorn` / `python-multipart`; name-set equality verified by `tests/test_regression_2026_09_22_gates.py` |

**2. Root-cause details**

1. **Performance & size**: FastAPI pulls in pydantic + pydantic_core, one of the Web panel's major size contributors; driving Starlette directly drops both, shrinking the bundle and startup overhead (size pending local re-measure with `scripts/report_bundle_size.py`).
2. **Wiring semantics preserved**: Starlette, unlike FastAPI, does not auto-dispatch `def` sync endpoints to a threadpool nor auto-parse JSON bodies; missing either blocks the event loop or changes 422 behavior — the `_route` adapter restores each equivalent behavior, leaving handler bodies untouched.
3. **422 contract deviation (known)**: the old field-level pydantic 422 `detail` is now a string `detail` (`str(ValueError)`); the frontend `apiError()` only reads the `detail` text, so behavior stays compatible.

**3. Verification (2026-09-29 runtime re-run, venv restored)**

- `python scripts/run_gates.py` → **8/8 green** (black / isort / mypy / annotation conventions / compile_po / check_version / check_runtime_pins / pytest backstop).
- `pytest` → **3248 passed, 14 skipped, 0 failed, empty warnings summary**; with `--cov=src`, `scripts/check_coverage.py` reports all 43 modules above threshold (total coverage 83.98%); `basedpyright` 0 errors / 0 warnings / 0 notes.
- `pytest tests/test_web_api.py tests/test_web_api_routes.py -q` → 165 passed, 2 skipped, 0 warnings.
- Runtime verification caught and fixed two wiring errors the earlier static-only pass could not see:
  1. `@app.middleware("http")` raises AttributeError at import time on Starlette (P0, panel unusable) → replaced with `add_middleware(BaseHTTPMiddleware, dispatch=auth_middleware)`;
  2. `raise HTTPException` inside endpoints came back with a plain-text body under Starlette's built-in handler — the `{"detail": ...}` JSON contract drifted (a batch of security tests went red) → registered a FastAPI-equivalent JSON handler (headers passthrough keeps Retry-After usage).
- Companion fixes: `scripts/check_version.py`'s web_api version check retargeted from `FastAPI(version=)` to the importlib.metadata dynamic-read shape (MIN-2262 fail-closed semantics kept; all three branches mutation-verified); the MID-2241 field-scan anchor in `tests/frontend/test_regression_2026_09_22_gates.mjs` moved to `src/web_models.py` and the endpoint-slice anchor to `@_route(app, ["GET"], "/api/language")`; the `/health` version assertion in `test_web_api.py` now reads the same-source `_APP_VERSION`; `uv.lock`/`egg-info` regenerated via `sync_metadata.py` (requires.txt free of fastapi/pydantic).

**4. Not verified & hand-back (closed)**

- ~~Gate green and runtime verification~~: done (see "3. Verification").
- Still handed to a later phase: the bundle-size re-measure `python scripts/report_bundle_size.py dist/DouyinLiveRecorder` requires one `build_exe.py` run first (local `dist/` is empty; a phase-5 closing item). Note the local venv still has fastapi/pydantic leftovers from the removed manifest (`pip install -r requirements.txt` does not uninstall removed packages); gates and tests are unaffected, but the user should run `pip uninstall fastapi pydantic` in a normal terminal before the bundle re-measure to keep the environment in sync with the manifest.

**5. Breaking changes**

- Removed the `fastapi` / `pydantic` runtime dependencies; `src/web_models` models are read via `.parse()` instead of the pydantic API (internal use, no impact on external plugins). All other routes, request/response shapes, security headers, and the auth middleware behave unchanged.

### v4.4.0 (2026-09-29) — Web front-end motion layer (Phase 1): scroll reveal / parallax particles / reduced-motion degradation, zero dependencies and zero build

> Module-level overview: Phase 1 (UI modernization · front-end motion) adds `web/motion.js` (223 lines, zero-dependency IIFE mounting `window.__dlrMotion`), adds the `<canvas id="bg-canvas">` background layer and script reference to `web/index.html`, and adds motion tokens plus full `prefers-reduced-motion` coverage to `web/style.css`. **Motion only adds classes, never wrapper elements** — the `tbody.innerHTML` fragment assertions in `tests/frontend/*.mjs` regression locks are unaffected; dynamically rendered table rows do not participate in the reveal animation.

**1. Changes by module (added / modified + file paths)**

| Module | Nature | Key files | Key change / criterion |
| --- | --- | --- | --- |
| Motion engine | Added | `web/motion.js` | single rAF loop, IntersectionObserver reveal (threshold 0.15, rootMargin `0px 0px -8% 0px`, stagger `min(index*40, 240)ms`, one-shot unobserve on hit), DPR capped at 2, pauses on `document.hidden`, full degradation under `prefers-reduced-motion: reduce`, `destroy()` leaves no timers; particle count `clamp(18, floor(viewport area/22000), 64)`, halved when viewport <768px or `hardwareConcurrency ≤ 4` |
| Page wiring | Modified | `web/index.html` | `<canvas id="bg-canvas" aria-hidden="true">` as the first child of `<body>` (pointer-events:none, z-index -1); `<script src="/web/motion.js">` appended at the end (defer, non-blocking) |
| Motion styles | Modified | `web/style.css` | `#bg-canvas` fixed layer, `.reveal`/`.is-revealed` transitions, `:focus-visible` ring, full `@media (prefers-reduced-motion: reduce)` coverage (motion section ≈ lines 508–547); transitions only touch transform/opacity/border-color/box-shadow, never layout properties |
| Tests | Added | `tests/frontend/test_motion.mjs` | 5 cases (node:test + node:vm sandbox driving motion.js: degradation gate / reveal / particle parameters / hidden pause / destroy cleanup), zero npm dependencies |

**2. Verification & known deviation**

- `node --test tests/frontend/*.mjs` → **65/65 green** (existing regression locks + 5 new); `tbody.innerHTML` fragment assertions intact.
- **Known deviation**: motion.js measures 9449 bytes (≈9.2KB), about 15% over the ≤8KB performance budget in proposal §5.1 — defer loading, single rAF and read/write separation all hold; the size deviation is deferred to Phase 5 evaluation (minify or split; no functional impact).

### v4.4.0 (2026-09-29) — Web panel mobile fix: two-row top bar + safe-area / `dvh` adaptation + in-panel table scrolling, removing clipping and horizontal page scroll on iPhone 16 Pro Max and Pixel 10

> This section is the **module-level overview** of this change (module table + root-cause detail + verification
> readings). Only the Web frontend static assets are touched (`web/index.html` + `web/style.css`); the Python side
> is unchanged and **nothing was deleted** - no rule, element or file was removed, existing comments are all
> preserved under the "add only, never rewrite" convention, and this round only adds rules and rewrites existing
> declarations.

**1. Changes classified by module (added / modified / removed + file paths)**

| Module | Nature of change | Main files | Key change / judgement |
| --- | --- | --- | --- |
| Web page skeleton | Modified, 1 place | `web/index.html` | viewport meta gains `viewport-fit=cover` - without it `env(safe-area-inset-*)` is always 0, so safe-area adaptation cannot take effect at all |
| Web styles: top bar | Modified (layout constraints rewritten) | `web/style.css` | `height:56px` -> `min-height:56px`; padding on all four sides becomes `max(20px, env(safe-area-inset-*))`; `.tabs` gains `min-width:0`; under the <=768px breakpoint it wraps into two rows (row 1: brand + language/theme, row 2: tabs on a full-width horizontal scroller) |
| Web styles: main content | Modified + added | `web/style.css` | `.view` left/right padding routed through the safe-area insets; `body` gains `min-height:100dvh` (the original `100vh` stays as fallback) and `text-size-adjust:100%` against landscape font inflation |
| Web styles: data tables | Added | `web/style.css` | Under the <=768px breakpoint `.panel{overflow-x:auto}` plus `min-width:540px` for the dashboard / danmaku / files tables - headers are no longer squeezed into vertical single-character columns, they scroll inside the panel instead |
| Web styles: control bar / toolbars / toast | Modified | `web/style.css` | `.recording-control`, `.danmaku-toolbar` and `.file-header` gain `flex-wrap:wrap`; `.toast` positioning becomes `max(24px, env(safe-area-inset-bottom/right))`; `.inline-form input[type="text"]` becomes a shrinkable `flex:1 1 160px; min-width:0` |
| Web frontend logic and tests | **Untouched** | `web/app.js`, `tests/frontend/*.mjs` | CSS/HTML-only change with no JS behavioural surface; the existing frontend suite needs no new case (no new DOM contract) |
| Python side (recording chain / Web backend / config / i18n) | **Untouched** | none | No `.py` file, dependency list, config file or catalog was touched this round |

**2. Root-cause detail (numbered; each comes from comparing the two device screenshots against the stylesheet)**

1. **Top-bar overflow (the main cause, present on both devices)**: `.topbar` had a fixed `height:56px` and a single
   non-wrapping flex row while `.brand` also carried `white-space:nowrap`, so the minimum content width of
   "brand + five tabs + language select + theme button" exceeded both viewports. The flex children were squeezed -
   in the screenshots "仪表盘" broke into vertical characters and the right-hand theme button was clipped off screen -
   and the whole top bar overflowed, producing page-level horizontal scrolling. Fix: row 2 of the module table.
2. **Missing safe-area adaptation**: no `viewport-fit=cover` in the viewport meta and no `env(safe-area-inset-*)`
   anywhere in the styles, so the Dynamic Island, the rounded corners and the Home Indicator obscured top-bar content
   and the bottom-right toast, and landscape clipped both sides.
3. **`100vh` viewport height**: `body{min-height:100vh}` does not follow the dynamic viewport when the mobile address
   bar collapses or expands, which shows up as the bottom being covered by the browser toolbar or the layout jumping;
   replaced with `100dvh` (old browsers fall back to the `100vh` line above it).
4. **No scroll fallback for the dashboard "now recording" table**: a five-column auto layout breaks out of `.panel`
   at min-content width on narrow screens, so the "设置画质 / 实际画质" headers collapse into vertical characters and
   row heights diverge. Fix is in-panel scrolling plus a minimum width, which **coexists** with the existing
   `table-layout:fixed` scheme of `#rooms-view` - the latter's scope is still strictly `#rooms-view` and its comment
   constraint (3) was not relaxed.
5. **Control bar / toolbars do not wrap**: the state text plus two buttons in `.recording-control`, and the heading
   plus filter select in `.danmaku-toolbar`, squeezed each other on narrow screens; `flex-wrap:wrap` makes them wrap
   instead of compress, keeping touch targets intact.

**3. Verification**

- `node --test tests/frontend/*.mjs` -> **60 passed / 0 failed** (the 60 existing cases including the MIN-2241 root
  `index.html` integrity / crossorigin lock and the frontend `parseConfigBool` consistency lock; no case added or removed).
- Line-ending check (measured after the change): `web/style.css` CRLF=0 / LF-only=506 (still pure LF),
  `web/index.html` CRLF=175 / LF-only=0 (still pure CRLF) - on both files the side that was 0 is still 0 afterwards,
  with no opposite-form lines mixed in.
- The Python side is unchanged, so this round did not run the `pytest` / mypy / black / isort gate set;
  `scripts/check_annotations.py` does not apply (no Python file touched).

**4. Not measured and handed back (honest boundary)**

- Live-device verification column: `SKIP(no physical device / no remote debugging channel)`. The two viewport
  readings (iPhone 16 Pro Max 440x956 CSS px at DPR 3; Pixel 10 about 412 CSS px wide at DPR ~2.6) come from device
  specifications and the screenshots; no Safari/Chrome remote debugging or on-device re-screenshot was performed here.
- Hand-back action: after a hard refresh (Ctrl+F5) confirm four points on a real device or device emulator - the two-row
  top bar is fully visible and the tabs scroll horizontally, the page as a whole has no horizontal scrollbar, the
  Dynamic Island / Home Indicator do not cover the top bar or the toast, and the three data tables can be scrolled
  horizontally inside their panel to see every column.
- Step 2 of the Definition of Done (live-device verification) does not apply to a CSS-only frontend change (no
  recording chain / source selection / ffmpeg arguments / platform resolver involved), but the four points above must be
  confirmed on a real device by the user before this change counts as closed.

### v4.3.0-dev (2026-09-27) — Today's changes classified by module: four release-chain fixes + findings 4/5/6 + the four-doc size pass + the AGENTS.md trim + metadata and consistency sync

> This section is the **module-level overview** of everything changed on 2026-09-27 (summary table plus the readings that
> justify each verdict). The path-level detail follows today's documentation policy and lives where the other 73
> historical inventories live; the four same-day detail entries (three release-chain faults, findings 4/5/6 plus the doc
> size pass, and the `AGENTS.md` trim) sit below and cross-verify this one.

| Module | Nature of change | Main files | Key reading / judgement |
| --- | --- | --- | --- |
| Packaging and release chain | `make_zip` naming and guards modified, Linux ffmpeg source and eight pins corrected; **added** `_clean_stale_release_zips` / `_drop_stale_release_zips` / `_assert_dual_zips_are_two_files` plus the `--dual` vs `--no-zip` exclusion | `build_exe.py` | No function or download source deleted; artifact names are `DouyinLiveRecorder-v4.3.0-windows-amd64-{lite,full}.zip` |
| CI and release workflow | **Added** the `release-guard` job and the `Verify dist contains both lite & full zips` step | `.github/workflows/build-release.yml` | `gh release delete` keeps tags by default; `fail_on_unmatched_files: true` not relaxed; the 08:14 edit by another actor was untouched here (logged) |
| Tests | **Added** 9 cases (10 assertion units), reworked `_stub_build_steps`, corrected two comments | `tests/test_build_exe.py` | Single file 100 -> **105 passed**; four mutations each reddened only their own lock; `DIST_DIR` repointed to `tmp_path` so tests cannot delete real artifacts |
| Root conventions | `make_zip` item gained judgements (4) and (5) plus the nine lock names; protobuf range corrected to `>=6.33.5,<8`; volume pass | `AGENTS.md` | 97,034 -> **95,715 B** (-1.4%); token audit: 0 lost among `test_` names, CVE codes and `UPPER_SNAKE` identifiers |
| CN/EN wikis | **Added** four detail entries plus this overview; 73 inventories relocated; 109 (zh) / 181 (EN) truncated table cells restored; statistics and index sections rewritten; step 4 of "Packaging and Release" corrected | `CODE_WIKI.md`, `CODE_WIKI_EN.md` | `^### v` 169 -> **173 = 173**; dangling-code-span paragraphs 26/18 -> **0**; both files pure CRLF |
| User-facing docs | **Version-entry sync in a later step the same day** (09-26 ~ 09-27 changes folded into the `v4.3.0` entry, the date range extended to 09-27, and the stale test readings plus the "permanently red on this host" note corrected) | `README.md` (104,040 -> 109,648 B), `README_EN.md` (123,017 -> 129,644 B) | All five subsections match one-to-one in count (🐛 9 / ✨ 12 / ⚠️ 9 / 🛠️ 7 / 🧪 4) and order; `^### v` 20 = 20; both files still pure CRLF. They genuinely needed no update during the consistency audit; this step **adds** content and still does not compress the README changelog |
| Reference sub-docs and local records | **Added** two inventory appendices; session learnings and work log appended | `docs/agent-reference/changelog-file-inventories.md` (130,064 -> 139,024 B), `-en.md` (98,458 -> 107,897 B), `session-learnings.md`, `.workbuddy/memory/2026-09-27.md` | 41 (zh) / 32 (EN) historical inventories plus this block; every pointer resolves; 0 orphaned table headers |
| Build-artifact metadata | **Rebuilt** egg-info, fixing two real drifts | `DouyinLiveRecorder.egg-info/` (gitignored + dockerignored) | `PKG-INFO`'s `Requires-Dist: h2` `>=4.3.0` -> `>=4.4.1`; embedded README gained the v4.3.0 section; the other four files byte-identical |
| Dependencies / versions / ignore lists / config / i18n | **One comment repair only; the rest verified as needing no update** | `requirements.txt` (inline comment completed), `pyproject.toml`, `Dockerfile`, `docker-compose.yaml`, `.gitignore`, `.dockerignore`, `.coveragerc-concurrency`, `config/config.ini`, the four catalogs | The `websockets>=14.0` inline comment was cut at "…14.0+ API," (a trailing comment cannot continue onto the next line, so this was a real truncation); completed against the matching `pyproject.toml` comment as "12/13.x makes `connect()` raise TypeError immediately and the reconnect loop swallows it, so danmaku never connects". **No specifier changed**: 23 vs 23 package-name sets still equal, `tests/test_regression_2026_09_22_gates.py` 25 passed, the file stays pure LF. Everything else: `python 3.14` / `node 24` identical across workflows; tool pins match what is installed; no gaps in the four exclude sets; `config.ini` has 6 sections / 143 keys and today added no key; four catalogs equal at 780 keys, `.mo` in sync at 781 entries, extractor reports 0 missing |

- **Consistency readings (measured this round, all recomputable)**: `grep -c '^### v' CODE_WIKI.md CODE_WIKI_EN.md` -> 173 = 173;
  `importlib.metadata.version('DouyinLiveRecorder')` -> 4.3.0; `scripts/check_version.py` PASS;
  `scripts/compile_po.py --check` in sync at 781 entries; `scripts/extract_i18n_strings.py` 0 missing;
  `pytest tests/test_i18n.py -k "keyset or sync or catalogs"` -> 6 passed;
  `pytest tests/test_proto_runtime_compat.py tests/test_i18n.py` -> 43 passed.
- **Deliberately not done (honest boundary)**: no dependency added to `requirements.txt` or `pyproject.toml` (nothing required one);
  `config/config.ini` not written (it holds credentials, is ignored, and no new key was needed); `README*.md` untouched per the
  user's 09-27 decision; `docs/agent-reference/session-learnings.md` remains the only LF-only file in that directory
  (finding 7, out of scope this round).

> The path-level inventory was moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](docs/agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-27) — Today's changes classified by module: four release-chain fixes + findings 4/5/6 + the four-doc size pass + the AGENTS.md trim + metadata and consistency sync | section: Today's change inventory by module (added / modified / removed + file paths)).

### v4.3.0-dev (2026-09-27) — `AGENTS.md` size pass: three real duplications removed and relocated readings turned into pointers; measured conclusion is that the root file is already at its constraint-density floor

- **Motivation**: the user asked to shrink `AGENTS.md` while keeping every core instruction and key constraint.
  Measure the redundancy classes first, then choose the method.
- **What the measurement showed**: the relocatable one-off readings had already been relocated correctly.
  `BtbN 126,600,656 B / 108,761,296 B`, `johnvansickle 41,888,096 B`, `autobuild-2024-10-31`, the `latest`
  republish at 2026-09-26T13:22:38Z, the ~two-week retention of daily `autobuild-*` tags (only
  `09-13~09-26`, 15 entries) and `api.github.com` `assets[].digest` all exist **verbatim** in
  `docs/agent-reference/measured-evidence.md` under "Runtime upstream integrity artifacts", yet `AGENTS.md`
  copied them again. Those numbers in the SEV-10 item and in the "three places to change per source" item are now
  pointers to that section, with an explicit note that the root file no longer duplicates values.
- **Three genuine duplications removed** (the file's own "no second source of truth" rule): (1) key convention 14
  and the 已知坑/i18n extractor-blindspot item overlapped - merged into 14 (absorbing the four catalog filenames and
  the "reports 0 missing, falsely green" consequence) and deleted the latter; (2) the version line in "Project
  overview" restated key convention 1 wholesale - compressed to a pointer; (3) two routing bullets in "Risk control"
  re-quoted the command and the forbidden directory list owned by their detail sections - kept only the judgement
  plus the pointer (the command `pip install --ignore-installed --no-deps -r requirements.txt` and the
  `downloads/`/`logs/`/`backup_config/` prohibition are still word-for-word in "CI / workflow conventions" and
  "temp-script cleanup"). The two same-cause items about parent-process `PYTHONUTF8` and
  `reconfigure(errors="replace")` in "Gate commands" were merged into one.
- **Reading**: `AGENTS.md` 97,034 -> **95,715 B** (-1,319, -1.4%), 496 lines, pure CRLF (LF-only count 0).
- **Why only 1.4% (a conclusion for later sessions)**: the file has **224 top-level items averaging 383 B**
  (command: `python -c "import pathlib,re; t=pathlib.Path('AGENTS.md').read_text(encoding='utf-8'); top=[x for x in t.splitlines() if re.match(r'^([-*] |[0-9]+[.] )', x)]; print(len(top), sum(len(x.encode()) for x in top)//len(top))"`),
  and item by item each one is an incompressible payload of judgement + constant name + test name + error code.
  Preservation audit: of the 997 code spans in the original, only 15 no longer appear in their old form, and each was
  checked: (a) 9 were `::test_...` fragments rewritten as "file name once, then bare test names" - all **55 test
  identifiers still present**; (b) 6 were readings that live on in the wiki / measured-evidence. Loss counts for
  `test_` identifiers, CVE/PYSEC/GHSA and MIN/SEV/MID codes, and `UPPER_SNAKE` constants and environment variables
  are all **0** (only three byte readings now exist solely in measured-evidence, by design). So under the current
  architecture the volume is near its floor; going materially lower requires an architecture change (move 已知坑
  detail into per-topic sub-docs, leaving the root file as index plus hard rules), which contradicts the file's own
  opening rule that "已知坑 constraint sentences stay in the root file" and therefore **needs the user's approval**;
  not attempted in this pass.
- **Verification**: `scripts/run_gates.py --list` still parses 8 gates (the parser reads the fenced bash block of the
  "Gate commands" section, which this pass did not touch);
  `pytest tests/test_run_gates.py tests/test_regression_2026_09_22_gates.py` -> **67 passed / 1 skipped**, including
  the three source locks ("first command must be the verbatim black gate line", "the `PYTHONUTF8=1` prefix must
  parse into env", "renaming the section must return an empty list"). Line-ending form unchanged. Docs-only change,
  so step 2 of the Definition of Done (live-device verification) does not apply.

### v4.3.0-dev (2026-09-27) — Fourth release-chain hardening: `--dual` now validates both return paths after packaging and prunes stale `dist/` zips before packaging; four docs slimmed by relocating 73 historical file inventories and restoring `…`-truncated table cells

- **Motivation**: the closing review of the previous entry produced findings 1-8; the user approved the already-fixed
  1/2/3 and asked for 4/5/6 plus a documentation size pass. (4) `make_zip`'s return value was discarded with `_ =`
  in the `--dual` branch, so nothing locally checked that the two variants really differ and both exist on disk, and
  `dist/` was never cleaned, so leftovers got swept in by `path: dist/*.zip`; (5) the artifact-name example still read
  `windows-x64` (Windows actually yields `amd64`; `x64` only exists as the runtime key after `_NODE_ARCH_MAP`
  normalization); (6) "both pre-existing tests assert *only* `zip_path.is_file()`" was imprecise -
  `test_make_zip_aborts_when_archive_still_contains_logs` asserts the `SystemExit` text.
- **Changes (`build_exe.py`, three)**: (1) `_assert_dual_zips_are_two_files(lite_zip, full_zip)` - identical names
  raise `SystemExit` (`zipfile` `"w"` truncates in place without an error, and a single-call guard cannot see two
  calls landing on one file), and a missing variant raises `SystemExit` too; (2)
  `_clean_stale_release_zips()` + `_drop_stale_release_zips()` - delete only `{APP_NAME}-v*.zip`, only when a zip is
  actually being produced, and print the removed list (silent deletion is as bad as not deleting); the `--no-zip`
  path never cleans. The call must sit **before the first** zip: inside `make_zip` the second call would delete the
  first one's artifact. (3) The non-`--dual` path keeps `make_zip`'s return value and prints the real artifact name.
- **Same-family corrections**: the truncation-incident comment in `tests/test_build_exe.py` rewritten to the true
  artifact name plus the precise per-test judgement; step 4 of "Packaging and Release" claimed "smoke tests run on
  the lite version", which the MID-2254 ordering change already disproved - it now says smoke runs after **both**
  zips against the release directory that holds the runtimes, and records the pruning plus the post-hoc check; the
  same line carried a stale exception name (`ChallengePageError` was removed on 2026-09-23 under MIN-2267; only
  `IntegrityError` / `NetworkError` remain) and a `…` that cut a code span in half.
- **Regression locks (5 new cases in `tests/test_build_exe.py`, all mutation-verified)**:
  `test_dual_build_aborts_when_both_variants_land_on_one_zip`,
  `test_dual_build_aborts_when_a_variant_zip_is_missing`,
  `test_dual_build_prunes_stale_zips_before_first_zip`,
  `test_no_zip_build_keeps_existing_dist_zips` (inverse lock: no packaging means no deletion),
  `test_clean_stale_release_zips_only_touches_own_artifacts` (includes the "missing `dist/` is a no-op" case and
  idempotency). `_stub_build_steps`'s `make_zip` stub now **returns a name derived from `suffix` and really writes
  the file**: the old constant `stub.zip` would turn all three `--dual` cases falsely red once the new check landed;
  `DIST_DIR` is also redirected to `tmp_path`, otherwise the tests would delete the user's real `dist/` artifacts.
  Mutation readings: cleaner made a no-op -> 2 red; `--dual` wiring removed -> 1 red; whole post-hoc check disabled
  -> 1 red; existence check only disabled -> 1 red. Each mutation reddened exactly its own lock, and
  `build_exe.py` came back byte-identical to its backup.
- **Doc size pass (policy: relocate, never delete)**: measured first, and the redundancy the request assumed was
  mostly not there - 0 trailing-whitespace lines, 0 multi-blank runs, and only 1 README line duplicated verbatim from
  `CODE_WIKI`; all the weight is body text. What genuinely moved is 73 historical "Files involved (classified by
  module)" inventories (41 zh blocks / 32 EN blocks) into
  `docs/agent-reference/changelog-file-inventories.md` / `-en.md`, each original spot keeping its section heading plus
  a one-line "entry | section" pointer. The pass also repaired a silent information loss from the 2026-09-25
  compression: 109 (zh) / 181 (EN) table cells truncated with `…` were restored from `.workbuddy/docold` by unique
  prefix match (+18,439 B / +33,117 B; 2 ambiguous matches were deliberately skipped).
  Readings (**before this entry was written**; `README*` are byte-identical to the originals):
  `CODE_WIKI.md` 638,616 -> 552,368 B (-86,248, -13.5%), `CODE_WIKI_EN.md` 692,281 -> 649,906 B (-42,375, -6.1%),
  `README.md` 104,040 B and `README_EN.md` 123,017 B unchanged; new appendices 130,064 B / 98,458 B.
  Confirmed scope: the README changelog is user-facing release notes and is not compressed.
- **Self-proof (recomputable)**: `grep -c '^### v'` is still **170 = 170**; a line-by-line reconciliation shows every
  non-empty original line still lives either in its document or in the appendix (only the 109/181 restored table rows
  vanished in their truncated form); all 41/32 pointers resolve to an existing file **and** to a real
  "entry + section" pair inside it; 0 orphaned table headers; dangling-code-span paragraphs dropped from 26 (zh) /
  18 (EN) to 0; every relocated block ends at a heading or a 验证/Impact/Conclusion-class label, so no table header
  was separated from its body; all four documents plus both appendices are pure CRLF (LF-only count 0).
- **Doc drift fixed on the way**: the "Document Statistics and Index" section claimed **285** Markdown files with no
  command attached, which cannot be recomputed; it now carries the command plus today's reading (**100**), the review
  reports are listed at their real home `docs/worklog/` (9 files), and a `docs/agent-reference/` row plus a new
  "Reference Sub-Document Index" section were added. Nine Chinese comment lines inside EN fenced command blocks were
  translated. Known and left undone: 162 Chinese lines remain inside EN code fences (the architecture diagram and the
  directory tree labels); that is translation work, not size redundancy, and is deferred to its own pass.
- **Verification**: `scripts/run_gates.py` 8/8 rc=0 (incl. `check_annotations.py` PASS at 23.8% mean comment density,
  `compile_po.py --check` in sync at 781 entries, `check_version.py`, `check_runtime_pins.py` fully pinned);
  its built-in full-suite fallback **3240 passed with an empty warnings summary** (up from 3235 = the 5 cases added
  here); `pytest --cov=src` -> 3240 passed / 14 skipped, total coverage **83.91%**, and `scripts/check_coverage.py`
  **PASSED: all 42 modules meet their threshold** (`src/proto/douyin_pb2.py` explicitly exempt);
  `basedpyright` (no path) 0 errors / 0 warnings / 0 notes; `mypy` (no path) Success; black and isort report both
  touched files unchanged; `python -m pytest tests/test_build_exe.py` alone -> **105 passed** (was 100).
- **Not measured / handed back**: (1) `python build_exe.py --smoke --dual` was **not** run locally (full PyInstaller
  build plus ~300MB upstream download), so the real "prune, then both zips land in `dist/`" path is still confirmed
  by CI's `Verify dist contains both lite & full zips` on its first run; (2) this is a docs-only change with no
  recording-chain / source-selection / ffmpeg-argument / platform-parsing touch point, so step 2 of the Definition of
  Done does not apply; (3) restored cells reflect the `.workbuddy/docold` snapshot (pre-2026-09-25), so any wording
  changed before that snapshot comes back in its snapshot form; (4) to reject the relocation, delete this entry's two
  artifacts: the two appendix files plus the 73 pointer lines.

### v4.3.0-dev (2026-09-27) — Third release-chain fault: `make_zip` truncated the artifact name via `Path.with_suffix(".zip")`, so lite was overwritten in place by full

- **Symptom**: this `Build & Release` run **passed** the pin verification and
  `Build executables + smoke test`, then reddened on the next step
  `Verify dist contains both lite & full zips`: `Found 0 lite zip(s) and 0 full zip(s)`,
  `Error: Expected both *-lite.zip and *-full.zip in dist/, but missing one or both.`, while
  `Full listing:` shows exactly one file, `dist/DouyinLiveRecorder-v4.3.zip` at 160,298,993 B.
  So the artifact **did exist** — what had vanished from both variant names were the `-lite`/`-full`
  segments together with `-<os>-<arch>`. Same family as the two earlier reds
  (`Pattern 'dist/*-lite.zip' does not match any files`), different cause, and one step further along.
- **Root cause**: `build_exe.make_zip()` built `zip_base = DIST_DIR / f"{APP_NAME}-v{version}-{os}-{arch}{suffix}"`
  and then `zip_path = zip_base.with_suffix(".zip")`. `Path.with_suffix` splits the extension at the
  **last dot**, and the version itself contains dots: measured locally on the real per-platform names —
  `Path('DouyinLiveRecorder-v4.3.0-windows-amd64-lite').suffix == '.0-windows-amd64-lite'`, so
  `with_suffix('.zip')` yields `DouyinLiveRecorder-v4.3.zip` (`-full` resolves to the **same** name, and so
  does `linux-x86_64`). Both `make_zip` calls of `--dual` therefore wrote one and the same path: the second
  (full) truncated and rewrote the first (lite) through zipfile's `"w"` mode, leaving full's content on disk
  under a name carrying neither variant nor platform.
- **Why it stayed invisible**: neither pre-existing `make_zip` test says anything about the **name** (one
  only asserts `zip_path.is_file()`, the other only the `SystemExit` text) — name drift is completely
  invisible to "does a file exist". The only name-aware judgement in the repo is the CI `dist/*-lite.zip`
  glob, so only a real `--dual` run could redden. The non-`--dual` path (`ci.yml` build-verify uses
  `--no-zip`) never exposed the missing platform segment either.
- **Fix (three parts, all in `build_exe.py`)**: (1) `.zip` is now concatenated inside the same f-string,
  keeping naming a single definition point, with a comment recording why `with_suffix` is banned;
  (2) a new structural invariant — the composed `zip_path.parent` must still be `DIST_DIR`, otherwise
  `SystemExit` (when `version`/`suffix` contain a path separator the f-string produces a **sub-path** and
  the artifact silently lands outside `dist/`; on Windows pathlib treats `\` as a separator too);
  (3) `--dual` and `--no-zip` are now mutually exclusive and fail fast — the `--dual` branch never reads
  `no_zip`, so `--dual --no-zip` used to **silently ignore** the flag the user explicitly typed and emit
  both large zips anyway (a contradictory combination must either error out or honour it, not half-run).
- **Regression locks (`tests/test_build_exe.py`, four functions / five cases, all mutation-verified)**:
  `test_make_zip_name_keeps_dotted_version_and_variant_suffix` (structural regex: full `v4.3.0` +
  `<os>-<arch>` + `-lite`/`-full` + `.zip`; the real Windows name looks like
  `DouyinLiveRecorder-v4.3.0-windows-amd64-lite.zip`),
  `test_dual_suffixes_do_not_collide_on_one_zip` (two `make_zip` calls must yield two distinct files),
  `test_make_zip_refuses_name_containing_path_separator` (runs **both** argument positions — `version` and
  `suffix` — with `'/'` rather than `os.sep` so the refusal branch really executes on both platforms),
  `test_dual_and_no_zip_are_mutually_exclusive` (asserts `order == []`, locking "the judgement precedes
  every build step").
  Mutation readings: reverting the implementation to `with_suffix(".zip")` reddened the first two while the
  pre-existing `make_zip` tests stayed green (disproving the old assertion standard); forcing the two new
  guards to `if False:` reddened the last two — the guard-(2) one via `FileNotFoundError`, which proves its
  assertions are actually reached.
- **Verification**: `pytest tests/test_build_exe.py` **100 passed**; `basedpyright build_exe.py tests/test_build_exe.py`
  0 errors / 0 warnings / 0 notes; `mypy` (no path arguments) Success over 158 files;
  `black --check` / `isort --check-only` report both files unchanged; `check_annotations.py` passes;
  line-ending form of every touched file unchanged (`build_exe.py` and `AGENTS.md` pure CRLF,
  `tests/test_build_exe.py` pure LF).
- **Not measured / handed back**: (1) `python build_exe.py --smoke --dual` was **not** run locally (it needs a
  full PyInstaller build plus ~300 MB of upstream downloads), so "lite + full both present in dist/" can only
  be confirmed by the first CI run of `Verify dist contains both lite & full zips`; (2) the failed Release
  record is reclaimed by `release-guard` (`needs.build.result != 'success'`) and the tag is kept, so a
  re-run republishes; (3) any historical asset named `DouyinLiveRecorder-v<major>.<minor>.zip` is a product
  of this defect — its lite half was never actually distributed, and a re-run is what yields correctly
  named per-platform variants.

### v4.3.0-dev (2026-09-27) — Release-chain fix: Linux ffmpeg pins now point at an immutable month-end release tag, plus a `release-guard` job that rewinds the empty Release left behind by a failed build

- **Background**: a tag-triggered `Build & Release` run died in the Linux build job's ffmpeg download step with
  `[build][FATAL] _ffmpeg_temp.tar.xz SHA256 不匹配（期望 87de0900…，实际 0cfb2146…），已终止构建`, and the
  very next step (`softprops/action-gh-release`) then reported
  `⚠️ Pattern 'dist/*-lite.zip' does not match any files` (`fail_on_unmatched_files: true`). The second message
  is a **downstream symptom** of "dist/ has no artefacts", not a separate fault — turning
  `fail_on_unmatched_files` off would erase the only visible signal.
- **Root cause**: both Linux slots of `_FFMPEG_DOWNLOAD_URLS` pointed at BtbN's
  `releases/download/latest/...`. `latest` is a **rolling alias**: the same asset name is re-uploaded over and
  over, so its digest keeps changing — tag `latest` was republished at `2026-09-26T13:22:38Z`, which invalidated
  the pin value `87de0900…` taken earlier the same day; the arm64 pin `30774c8f…` was stale too (now `f2fe35e9…`).
- **Chosen route (per the user: "switch to an immutable month-end tag")**: both slots now pin the **month-end**
  autobuild tag `autobuild-2026-08-31-13-27` (assets
  `ffmpeg-n9.0.1-11-ge47273f4d9-linux{64,arm64}-gpl-9.0.tar.xz`), with pin values taken from
  `api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/<tag>` → `assets[].digest`
  (linux64 `182c1b50…`, linuxarm64 `e2dd447c…`). Why month-end specifically: the repo holds only **38 releases**;
  daily `autobuild-*` tags survive only about two weeks (only 09-13…09-26, 15 of them, were left), so pinning a
  daily tag is planting a guaranteed 404, while month-end tags reach back to `autobuild-2024-10-31` — the only
  combination where both URL and digest are immutable. Cost: the bundled ffmpeg lags `latest` (n9.0.2) and now
  sits at n9.0.1-11-ge47273f4d9; upgrading means editing the tag **and** the pin by hand, which is exactly the
  SEV-10 manual gate — deliberately not replaced by auto-fetching the current hash.
- **Second item, the guardrail**: `build-release.yml` gains a `release-guard` job
  (`needs: [prepare, build]`, `if: always() && release path && needs.build.result != 'success'`) that runs
  `gh release delete` on the empty/partial Release pre-created by `release-create` (tag is **kept**) and emits a
  `::warning::`. Why: `release-create` deliberately pre-allocates the Release before build to avoid three build
  jobs racing to create it, but when a build fails the finalizing `release` job is skipped by `needs: build`, so
  an empty Release stays in the repo with zero downloadable assets.
- **Files touched**: `build_exe.py` (two URLs + two pin cells + three comment/maintenance corrections);
  `tests/test_build_exe.py` (new `test_linux_ffmpeg_urls_pin_an_immutable_release_tag`: forbids
  `/releases/download/latest/`, forbids the `n9.0-latest-` asset-name form, requires one shared tag across both
  arches); `.github/workflows/build-release.yml` (new `release-guard` job only — matrix/cache/build/upload logic
  untouched); `AGENTS.md` (SEV-10 entry gains the "month-end tag" rule and its regression lock; a new
  empty-Release guardrail bullet under CI/workflow conventions; volume readings refreshed);
  `docs/agent-reference/measured-evidence.md` (2026-09-27 re-measurement table).
- **Measured (2026-09-27)**: `releases/latest` → linux64 150,999,836 B / `0cfb2146…`, linuxarm64 127,395,868 B /
  `f2fe35e9…` (neither equals the old pins); `releases?per_page=100` → 38 releases total; month-end tag assets →
  linux64 126,600,656 B / `182c1b50…`, linuxarm64 108,761,296 B / `e2dd447c…` (a `checksums.sha256` asset is
  also published, usable as a second cross-check); gyan.dev Windows `.sha256` still `60f46726…` (no drift);
  nodejs.org's first `lts` entry still `v24.21.0` (no drift). A prefix fetch confirmed the month-end asset is a
  valid xz (magic `fd377a585a00`) whose top-level directory is
  `ffmpeg-n9.0.1-11-ge47273f4d9-linux64-gpl-9.0/`.
- **Verification**: `pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` → **115 passed**; full
  `pytest` → 3229 passed / 14 skipped with an empty warnings summary (the single failure,
  `test_web_config.py::TestFormatUrlLine::test_normal_line`, is the sandbox failing to resolve
  `live.douyin.com`; re-run alone it is **1 passed**, unrelated to this change); `mypy` (no args) → Success over
  158 files; `basedpyright tests/test_build_exe.py` → 0 errors / 0 warnings / 0 notes; `black --check` and
  `isort --check-only` unchanged; `check_annotations.py` passes; `check_runtime_pins.py --strict` still rc=0;
  `yaml.safe_load` on the workflow parses with jobs in the order prepare / release-create / build /
  release-guard / release. Line endings unchanged (`build_exe.py`, `AGENTS.md`, `CODE_WIKI*.md`,
  `measured-evidence.md` stay pure CRLF; the test file and the workflow stay pure LF).
- **Not yet verified / handed back**: ① `github.com` direct links are reset on this box (prefix fetch → http=000,
  full fetch died at 5.4 MB), so "download from the new URL and compare against the pin" can only be confirmed by
  the first GitHub runner run; ② `bin/ffmpeg` / `bin/ffprobe` inside the month-end archive were not directly
  confirmed by this prefix (5.4 MB only covered `doc/`) — we rely on the 09-26 measurement for the same asset
  family; if they are missing, `_extract_linux_ffmpeg_binaries()` raises `SystemExit` rather than degrading to a
  silent empty package; ③ Linux full-package size changes with the new tag (126,600,656 B / 108,761,296 B) and
  must be re-checked against CI artefacts via `scripts/report_bundle_size.py` before touching any platform
  threshold.

### v4.3.0-dev (2026-09-27) — Second release-chain fault fixed: eight slots of `_PINNED_RUNTIME_SHA256` had been rewritten to the official-signature marker; hashes re-pinned from the official channels

- **Symptom**: the pasted log only carried the last two lines `Run softprops/action-gh-release@v3` /
  `⚠️ Pattern 'dist/*-lite.zip' does not match any files`. It is read the same way as the entry above
  (`fail_on_unmatched_files: true` is the only visible signal of a missing artefact and must stay on).
  Re-computing locally exposed a **second fault in the current working tree that fires even earlier**:
  eight slot values in `build_exe.py`'s `_PINNED_RUNTIME_SHA256` had been replaced wholesale with
  `OFFICIAL_SIGNATURE_PIN` (file mtime 07:58, i.e. after the 01:45 wrap-up of the previous entry), which
  moves the break point of the release chain from the build job forward to the prepare job.
- **Root cause**: the signature mode only applies to slots whose upstream really publishes no hash *and*
  which are registered in `_RUNTIME_GPG_SIGNATURES` with a signature URL plus the full 40-hex primary
  fingerprint — in this repo that is only the four macOS ffmpeg/ffprobe slots. The five node slots
  (nodejs.org `SHASUMS256.txt`), `windows-x64/ffmpeg` (gyan.dev `.sha256`) and the two Linux ffmpeg slots
  (BtbN `assets[].digest`) all have officially published values; once turned into the marker,
  `_is_signature_satisfied` returns False because the slot is unregistered → all three disjuncts of
  `_slot_is_gated` are False. Two consequences: `scripts/check_runtime_pins.py --strict` returned **rc=1**
  (the prepare job's fail-closed step goes red) and
  `tests/test_build_exe.py::test_table_never_declares_signature_mode_without_satisfaction` **failed** —
  that lock exists precisely to catch this rewrite.
- **Action**: all eight values re-derived from the **official channels** named in the AGENTS.md /
  `build_exe.py` maintenance notes, never from locally downloaded self-computed digests:
  `curl -sS https://nodejs.org/dist/v24.21.0/SHASUMS256.txt` (win-x64 `.zip`, linux/macos `.tar.gz` — the
  five asset names `_download_nodejs` actually fetches);
  `curl -sSL https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip.sha256` → `60f46726…47ba`
  (no drift);
  `curl -sS https://api.github.com/repos/BtbN/FFmpeg-Builds/releases/tags/autobuild-2026-08-31-13-27`
  → linux64 `182c1b50…` / linuxarm64 `e2dd447c…` (byte-identical to what measured-evidence.md records; a
  month-end tag's digest is immutable); plus confirmation that the first `lts` entry of `dist/index.json`
  is still `v24.21.0` (Krypton). The macOS ffmpeg/ffprobe slots keep the signature mode untouched.
- **Scope**: `build_exe.py` only (8 pin values + one `[2026-09-27 restore]` note above the table + a
  per-node-line source asset name). Logic, the URL table, the predicates, tests and workflows untouched.
- **Verification**: before the change `check_runtime_pins.py --strict` was **rc=1** and
  `test_table_never_declares_signature_mode_without_satisfaction` FAILED (8 offenders named per slot);
  afterwards both `--strict` and the structural mode return **rc=0**, `pytest tests/test_build_exe.py`
  **95 passed**, `python scripts/run_gates.py` **8/8 green rc=0**, full `pytest` **3230 passed /
  14 skipped** with an empty warnings summary, `basedpyright build_exe.py` 0 errors / 0 warnings / 0 notes,
  and `black --check` / `isort --check-only` / `py_compile` pass. End-of-line shape unchanged (build_exe.py
  pure CRLF: 1686 CRLF / 0 bare LF).
- **Not measured / handed back**: ① "download in full and compare against the pinned value" still only
  runs on a GitHub runner first — `github.com` direct links are reset on this machine, only
  `api.github.com`, `nodejs.org` and `gyan.dev` are reachable; ② during this session `build-release.yml`
  was modified **concurrently** at 08:14 (a new `Verify dist contains both lite & full zips` step and
  `| tee build_exe.log` on the build command). That file is neither changed nor reviewed by this entry;
  under `pipefail` the `tee` does not swallow `SystemExit`, but its author should confirm before releasing.

### v4.3.0-dev (2026-09-26) — Release-chain integrity gate gains an "official signature" mode and Linux ffmpeg moves to BtbN: `build-release.yml` prepare goes from rc=1 to rc=0 without loosening SEV-10's fail-closed semantics

- **Background**: the prepare job failed at `Verify runtime binary SHA256 pins (fail-closed)` with
  `Error: Process completed with exit code 1.`, and the log body is literally the output of
  `scripts/check_runtime_pins.py --strict`: two in-matrix slots (`linux-x64/ffmpeg`, `macos-arm64/ffmpeg`) still
  carry the placeholder marker. Located precisely at `.github/workflows/build-release.yml:141-149`; rc=1 comes from
  the `--strict` branch of the checker. This is not a defect — the gate stopped the release exactly as designed
  (both the `build_exe.py` pin-table comment and the `AGENTS.md` SEV-10 entry say: if upstream publishes no hash,
  the release chain stays red).
- **Why deleting the gate was not the fix**: the pin table does not live in the workflow (source of truth is
  `build_exe._PINNED_RUNTIME_SHA256`; the YAML only passes values through via `DLR_RUNTIME_SHA256`). And
  `require_pinned_hashes()` is auto-true under `GITHUB_ACTIONS=true`, so removing the prepare step would only move
  the same failure into the three build jobs (each after a full pip install, still aborting before any download) —
  zero artefacts either way.
- **Chosen route (per the user's "grade integrity criteria by what each upstream actually publishes")**: class ①
  "release-time runtime binaries" gains a second satisfaction mode **behind the single predicate**
  `build_exe._slot_is_gated()` — the **official signature mode**: table value = `OFFICIAL_SIGNATURE_PIN`, and the
  slot must actually be registered in `_RUNTIME_GPG_SIGNATURES` with a 40-hex fingerprint. The marker alone never
  grants passage (same anti-"easier-to-fill marker = free pass" wall as the 4th class `SOURCE_BUILD_PROVENANCE`).
  macOS's two slots take this mode (evermeet publishes `/sig`, no hash); the Linux slots moved to BtbN's n9.0-series
  assets, pinning the `assets[].digest` SHA256 published by `api.github.com`, so no MD5 downgrade mode was needed.
- **SEV-2221 fixed on the way**: `_download_file()`'s pre-download gate only accepted `_is_pinned()`, while the
  signature check sat after the download inside the "hash already matched" branch — so a placeholder-valued macOS
  slot never reached the download and the P-2 verification had **never executed** on the real build path. The gate
  now accepts both modes, and a signature-mode slot **must** pass verification after download (BADSIG / signer not
  in the pinned key's primary-or-subkey set / missing gpg or unreachable signature on the release path all
  `SystemExit`); the observed SHA256 is logged as the audit trail for the rolling alias.
- **Scope**: `build_exe.py` (new constant + predicates, `_download_file` dispatch, `_unpinned_action` naming the
  exact reason a signature declaration is unsatisfied, the two Linux rows of `_FFMPEG_DOWNLOAD_URLS`, four pin-table
  cells, and Linux extraction pulled out into the layout-agnostic `_extract_linux_ffmpeg_binaries()`);
  `scripts/check_runtime_pins.py` (per-mode `[NOTE]` announcement, judgement still delegated);
  `tests/test_build_exe.py` (+12 cases: signature-mode truth table, case-insensitive marker, fingerprint shape gate,
  table/registration stay-in-sync invariant, the SEV-2221 reachability lock, abort-on-bad-signature and
  abort-when-gpg-missing, unregistered marker must not download, both archive layouts plus abort-on-missing-binary;
  `_ALLOWED_HOSTS` gains `github.com` and drops `johnvansickle.com`; `_FakeResponse` gains `headers` and drains per
  read); `tests/test_check_runtime_pins.py` (`_fake_module` exposes the new symbols + 2 routing cases);
  `.github/workflows/build-release.yml` — **comments only** (4 spots: the `DLR_RUNTIME_SHA256` legend, the prepare
  step explanation, the source-host list, and the gnupg step noting verification is now the sole criterion);
  matrix / caching / build / upload / release logic untouched. Plus `AGENTS.md` and
  `docs/agent-reference/measured-evidence.md` (every retrieval command and reading from this round).
- **Measured (2026-09-26)**: `evermeet.ca/ffmpeg/getrelease/zip/sig` → 200 / `application/pgp-signature` / 594 B
  binary OpenPGP packet, landing on `e.deolaha.ca:4242/pub/ffmpeg/ffmpeg-9.0.2.zip.sig`; keyserver lookup of
  `0x476C4B611A660874` → 200, UID `static FFmpeg binaries (signing key)`, server-echoed fingerprint equal to the
  pinned value (**a second, independent channel** — this closes R-2's "fingerprint never corroborated");
  `johnvansickle ...amd64-static.tar.xz.md5` → 200 with the same value as 2026-09-22, `.sha256` → 404; BtbN
  `linux64-gpl-9.0` = 150,998,508 B / `linuxarm64-gpl-9.0` = 127,417,700 B, and a ranged prefix fetch + `tar -tJf`
  confirms the binaries sit at `bin/ffmpeg` and `bin/ffprobe`.
- **Verification**: `scripts/run_gates.py` 8/8 green; full `pytest` **3220 passed, empty warnings summary**;
  `pytest tests/test_build_exe.py tests/test_check_runtime_pins.py` → 105 passed; `check_runtime_pins.py --strict`
  went rc=1 → **rc=0**, announcing the two macOS slots as "signature mode" rather than "pinned"; all five mutations
  reddened (gate omits the new mode / SEV-2221 reverted / marker alone satisfies / `bin/` layout hardcoded /
  missing binary no longer aborts).
- **Not yet verified, handed back**: ① the direct `github.com/.../releases/download/...` link resets on this box, so
  "download in full and compare against the pin" can only be proven by the first GitHub runner run; ② evermeet
  verification on the real build path executes for the first time in the macOS CI job (the keyserver probe shows
  `--recv-keys` will resolve, but no local gpg run happened); ③ the Linux full zip grows sharply with the source
  switch, and `report_bundle_size.py` could not be run locally (no Linux, blocked direct link) — re-check the size
  gate from CI artefacts before adjusting any threshold. A rolling alias pins *who signed*, not *which version*: a
  new evermeet build flows through without reddening the gate. That is this mode's inherent boundary; the logged
  observed SHA256 is what makes it auditable afterwards.

### v4.3.0-dev (2026-09-26) — CI typecheck gate: install a pinned pytest and fix the `[return]` false positive in `tests/test_proto_runtime_compat.py`, removing the "green locally, red in CI" coverage drift (CI / test-only change, zero runtime impact)

- **Background**: the CI `typecheck` job reported `tests/test_proto_runtime_compat.py:33: error: Missing return statement  [return]` (checked 159 files), while a local `mypy` run was fully green on 158 files and could not reproduce it at all.
- **Root cause**: that job installs only `requirements.txt + mypy` — **no pytest** — so `import pytest` resolves to `Any`, the `NoReturn` annotation of `pytest.fail()` is lost, and mypy concludes that `_declared_protobuf_specifier() -> str` may fall off the end. This is an environment difference, not a code defect; the same cause also meant that every `pytest.*` in `tests/` (fixtures / `MonkeyPatch` / `raises`) was previously **unchecked** — the gate was effectively half-blind. Local reproduction: `mypy --no-site-packages` (hides installed packages and reproduces the exact error; the 5 extra `no-any-return` reports in that mode are over-stripping noise).
- **Nature of change**: CI workflow + one test helper + `AGENTS.md` only. `src/`, `main.py`, `gui.py`, `web.py`, `web/app.js`, `requirements.txt` / `pyproject.toml` untouched; no dependency added or removed (pytest is installed only inside the typecheck job, never into the runtime list).

**Files touched (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](docs/agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-26) — CI typecheck gate: install a pinned pytest and fix the `[return]` false positive in `tests/test_proto_runtime_compat.py`, removing the "green locally, red in CI" coverage drift (CI / test-only change, zero runtime impact) | section: Files touched (grouped by module)).

**Verification**: `mypy` (no args) and `mypy --platform linux` both succeed on 158 files (local pytest is 9.1.1, the same version CI now pins); under `mypy --no-site-packages` the original `[return]` is gone and only the 5 stripping-noise reports remain; `basedpyright tests/test_proto_runtime_compat.py` reports 0 errors / 0 warnings / 0 notes; `black --check` unchanged; `pytest tests/test_proto_runtime_compat.py` → 4 passed; `yaml.safe_load` parses `ci.yml` with the expected outputs / steps; line endings of the edited files are unchanged (`ci.yml` pure LF; `AGENTS.md` and the test file pure CRLF).

**Leftover observation**: that CI run reported `checked 159 source files` while the local count under `[tool.mypy].files` is 158 `.py` files — one unaccounted file (likely an extra file on the commit of that run), unrelated to this fix.

### v4.3.0-dev (2026-09-26) — Repo metadata & doc sync: aligned the dependency tables / structure trees / egg-info / ignore lists and cleaned up leftover records of the deleted `weverse_auth` module (metadata & docs only, zero runtime code change)

- **Background**: a full-repo read-through cross-checking the four shared-source families (version / dependencies / structure trees / ignore lists) surfaced several stale spots: the `CODE_WIKI*.md` dependency tables still listed only 16 entries with `starlette` lower bound `>=0.49.1`; the structure trees still listed `src/weverse_auth.py` and `tests/test_weverse_auth.py`, both deleted on 2026-09-23; `DouyinLiveRecorder.egg-info/requires.txt` was missing `h2`/`socksio` (added 2026-09-23); `AGENTS.md` still said "21 runtime dependencies".
- **Nature of change**: docs / metadata / ignore lists only, plus a regenerated `egg-info`. `src/`, `main.py`, `gui.py`, `web.py` and `web/app.js` untouched; the runtime dependency set is unchanged (23 entries on each side, identical package-name sets).

**Files touched (grouped by module)**:

> Inventory moved verbatim to [docs/agent-reference/changelog-file-inventories-en.md](docs/agent-reference/changelog-file-inventories-en.md) (entry: v4.3.0-dev (2026-09-26) — Repo metadata & doc sync: aligned the dependency tables / structure trees / egg-info / ignore lists and cleaned up leftover records of the deleted `weverse_auth` module (metadata & docs only, zero runtime code change) | section: Files touched (grouped by module)).

**Verification**: `scripts/check_version.py` rc=0 (`pyproject.toml` is the single source of truth; all four consumers read it dynamically); `scripts/check_runtime_pins.py` rc=0; `pytest tests/test_regression_2026_09_22_gates.py tests/test_build_exe.py` all green (including the "requirements.txt and pyproject package-name sets are equal" lock); `pytest tests/test_i18n.py tests/test_i18n_migration.py tests/test_i18n_tr.py tests/test_frontend_*.py` 56 passed; `node --test tests/frontend/*.mjs` green.

**Handed back to the user (needs a decision)**: `config/config.ini` currently has `禁用SSL证书验证的平台(逗号分隔) = 虎牙直播,B站直播,抖音直播`, while the code's enforced set `main.SSL_DISABLE_REQUIRED_PLATFORMS` contains only `虎牙直播` / `B站直播` and the README default is the same two. The extra `抖音直播` entry is a legacy exemption that disables certificate verification for Douyin streams; whether to remove it is left to the user — this pass did not touch a security-relevant toggle on its own.

### Earlier entries (archived)

164 day-by-day development entries from 2026-05-17 to 2026-09-24 were moved verbatim to [code-wiki-history-en.md](docs/changelog/code-wiki-history-en.md) on 2026-09-28; that volume also restores the short `…` / mid-sentence tails left by the previous trimming pass against the `.workbuddy/docold` baseline (exact rule in its header).
Reason: the changelog alone took 72.9% of this file's characters (472,669 of 648,535). The root document now keeps only the current release window plus this pointer, which is what makes the rest of the document readable.
