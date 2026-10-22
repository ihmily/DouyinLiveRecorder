# Changelog File Inventories (CODE_WIKI_EN.md appendix)

> Verbatim copies of the 'Files involved (classified by module)' inventories that used to sit inline
> in the CODE_WIKI_EN.md changelog. Entries keep their section heading plus a one-line pointer here;
> the entry title and section name in that pointer are the locator. Produced by the 2026-09-27 doc
> size pass (pre/post originals under .workbuddy/docold).


## v4.3.0-dev (2026-09-26) — CI typecheck gate: install a pinned pytest and fix the `[return]` false positive in `tests/test_proto_runtime_compat.py`, removing the "green locally, red in CI" coverage drift (CI / test-only change, zero runtime impact)


### Files touched (grouped by module)

- **Module: `tests/test_proto_runtime_compat.py` (F-14 protobuf guard test)** — the trailing `pytest.fail(...)` of the helper `_declared_protobuf_specifier()` became `raise AssertionError(...)`: `raise` is inherently `NoReturn`, independent of whether pytest is visible, so both environments agree; no unreachable statement was appended after it (basedpyright would report `reportUnreachable`). `_satisfies()` in the same file ends with `return True`, so its `pytest.fail` was unaffected and left as is.
- **Module: `.github/workflows/ci.yml` (typecheck job)** — ① the setup job `outputs` gained `pytest_version`; ② the consts step declares `pytest_version=9.1.1` (pinned like black / isort / mypy, to prevent "CI turns red with no code change"); ③ Install dependencies now runs `pip install -r requirements.txt "mypy==2.3.1" "pytest==9.1.1"`, with the label updated to "requirements + mypy + pytest" and a comment explaining both why pytest is required and why it is pinned. `pytest` alone suffices: all 99 test files import only `pytest` and `from pytest import MonkeyPatch` — no `pytest_asyncio` / `pytest_mock` / `pytest_cov` imports (and missing ones are absorbed by `ignore_missing_imports`).
- **Module: `AGENTS.md` (known pitfalls)** — a new bullet under "Type checking, comments & static gates": the typecheck job must install pytest or `tests/` is half-blind; helper functions that cannot fall through must end with `raise AssertionError(...)` instead of relying on `pytest.fail()`'s return type. Includes the `mypy --no-site-packages` reproduction recipe and the note that the extra `no-any-return` reports in that mode are noise.


## v4.3.0-dev (2026-09-26) — Repo metadata & doc sync: aligned the dependency tables / structure trees / egg-info / ignore lists and cleaned up leftover records of the deleted `weverse_auth` module (metadata & docs only, zero runtime code change)


### Files touched (grouped by module)

- **Module: `AGENTS.md`** — runtime dependency count `21 → 23` (two places), with a note about when `h2`/`socksio` were added; the security-floor bullet now reads `starlette>=1.3.1` instead of `>=1.0.1` (1.0.1 itself still sits inside the PYSEC-2026-2280/2281/248/249 affected range; raised a second time on 2026-09-21).
- **Module: `README.md` / `README_EN.md`** — removed `src/weverse_auth.py` from the structure tree and added the previously missing `src/ffmpeg_master_download.py` (CN/EN in sync).
- **Module: `CODE_WIKI.md` / `CODE_WIKI_EN.md`** — (1) dependency table grown from 16 to 23 entries (added `urllib3` / `h2` / `socksio` / `websockets` / `protobuf` / `brotli` / `PyYAML`, `starlette` lower bound `0.49.1 → 1.3.1`, dropped the empty placeholder row); (2) removed the `weverse_auth.py` / `test_weverse_auth.py` leftovers from the structure and test trees; (3) "Note 1" converted from a current-state statement into a dated `[Historical note]` (keeping the "never add the pip `weverse` package" conclusion, since it pulls in pycrypto which does not compile). Historical changelog entries were left verbatim — they record what was true at the time.
- **Module: `DouyinLiveRecorder.egg-info` (build artifact, not committed)** — regenerated via setuptools `egg_info`: `requires.txt` now carries `h2>=4.4.1` / `socksio>=1.0.0`, `SOURCES.txt` ; `PKG-INFO` version stays `4.3.0`.
- **Module: `requirements.txt` / `pyproject.toml` (the two same-source dependency manifests)** — the `h2` lower bound goes `>=4.3.0` → **`>=4.4.1`**: the CI `deps-audit` "declared floors" step (pinning every `>=X` to `==X`, then auditing with `--no-deps`) reported `h2 4.3.0` as hit by **PYSEC-2026-3628 / GHSA-6hr6-w5qg-qmwg** (duplicate Host header → request smuggling), OSV range `introduced=0` / `fixed=4.4.1`. 4.3.0 only fixed the sibling PYSEC-2026-1435, so **the old floor itself sits inside the affected range** — exactly the same shape as starlette and protobuf, and the resolution-mode audit (which only looks at the newest version in range) is blind to it. Both the local install and `uv.lock` are already 4.4.1, so raising the floor does not change the resolved set; both manifests, `egg-info`, the `CODE_WIKI*.md` dependency tables and both README changelogs were updated in lock-step.
- **Module: `.dockerignore`** — added `_probe_*.py` (kept in sync with `.gitignore`; only `_out_*.txt` was excluded before).
- **Module: `config/config.ini` (local runtime config, git-ignored)** — added `ttwid` under `[Cookie]` (declared by `src/ttwid.py::_CONFIG_TTWID_KEY` and by the README, but missing locally); UTF-8 BOM and LF line endings preserved.
- **Module: `i18n/` (four catalogs)** — completeness check: `scripts/extract_i18n_strings.py` scanned 533 valuable strings, plus a targeted re-scan of its three blind spots (`print_colored` / `messagebox` / push templates): **0 missing**, key sets identical, no empty values. Cleanup: removed 3 orphan entries related to Weverse token refresh (the owning `src/weverse_auth.py` was deleted on 2026-09-23 and nothing in the repo emits them any more); all four catalogs moved **in lock-step** to **780 entries**, then `scripts/compile_po.py` regenerated `zh_CN.mo` (781 entries including the header / 110585 bytes).


## v4.3.0-dev (2026-09-24) — Build artifact size optimization: located and excluded runtime-unreachable modules + zip `compresslevel=9`; lite artifact 82.77MB → 64.88MB (−21.6%), zip 54.84MB → 42.19MB (−23.1%)


### Files touched

- **`build_exe.py`** — new module constant `BLOAT_EXCLUDES` (each entry carries its measured size, the unreachability argument and the Pillow tolerance evidence)…
- **`scripts/report_bundle_size.py` (new)** — artifact size report: totals / per-package aggregation / largest files / dev-toolchain leak detection…
- **`tests/`** — 5 new locks in `test_build_exe.py`: the exclude list must not hit anything production code really imports (AST-collected import names, one-way prefix match), the list must still cover the 6 measured bloat entries, all three Analyses must carry `excludes_bloat`, the i18n list must contain no `.po` but still carry `.mo/.json/.yaml`, and `_zip_release_dir` must keep the `APP_NAME/` prefix and deflate.
- **`AGENTS.md`** — new "Artifact size gate" subsection under build commands: measurement entry point, exclusion entry point and its admission criteria, the four irreducible fixed costs, and why `strip` / `upx` were evaluated and rejected.
- **Also noted (not part of this change)**: the full `pytest` run has one pre-existing, unrelated failure — `tests/test_ffmpeg_path_preference.py::TestSelfShadowGuard::test_symlinked_system_hit_inside_bundled_dir_keeps_prepending` simulates macOS symlink semantics (`sys_platform="darwin"`) and `os.path.realpath` normalizes differently on this Windows host…


## v4.3.0-dev (2026-09-24) — Type-stub de-coupling from `six`: the two abstract-base stubs in `typings/execjs/` now use `metaclass=ABCMeta`, clearing mypy `[import-untyped]` in the IDE's per-file check (stub-only, zero runtime impact)


### Files touched (classified by module)

- **Module: `typings/execjs/` (type stubs for the third-party PyExecJS)** — 2 `.pyi` files modified: `_abstract_runtime.pyi` and `_abstract_runtime_context.pyi` dropped `import six`, switched to the `metaclass=` form, and gained "why it changed + record of the old form" comments per the comment convention.
- **Rejected alternatives**: (1) adding `types-six` as a dev dependency — it would widen the installation surface for the sake of a single stub file and conflicts with the "dev dependencies never enter the runtime requirement list" convention…
- **Recorded in passing (no change made)**: when black is invoked with **explicit file arguments**, `_external_runtime.pyi` / `__main__.pyi` each have one line >120 characters that it wants wrapped (leftover from the 2026-09-24 annotation batch).


## v4.3.0-dev (2026-09-24) — Frontend regression-lock fixes + wired into CI: two red locks in `test_regression_2026_09_22_gates.mjs` diagnosed as test-side defects, `.py` wrapper added into the pytest/CI loop (zero production-code change)


### Files affected (grouped by module)

- **Module: `tests/frontend/` (`web/app.js` sandbox regression locks)** — 3 edits in `test_regression_2026_09_22_gates.mjs` (pure LF):
  -  The production `/` route already correctly returns `_WEB_DIR / "index.html"` — unchanged.
  - `makeElement` DOM stub gained `options: []`: the SEV-2228 second half "danmaku_unavailable must not advance the incremental cursor" reported `since=0` instead of `since=7`
  - Upgraded the SEV-2228 second-half assertion from 2 rounds to 3 (success → error → request again), adding an assertion that `calls[2]` is still `since=7`: the old form only asserted `calls[1]` (determined by req1's success response), so it could never observe the larger `last_seq:99` that req2's error response deliberately carries — a half-dead lock misaligned with its own title's promise.
-  **Reuses** `_run_node` / `_parse_node_summary` from `test_frontend_quality_ui.py` (the MID-64 regression-locked hardening: redirect output to a temp file + reap the whole process tree on timeout + always capture as bytes) instead of re-implementing the subprocess hardening…
- **Module: `.github/workflows/ci.yml` (test job frontend gate)** — changed the "Gate frontend tests not skipped" step: brought the new module in, and switched the criterion from "run the whole `test_frontend_quality_ui.py` module + grep `N skipped`" to **naming the two node-driven entry tests by node-id** — fixing a platform-induced false-red of this step on ubuntu (two `skipif(sys.platform != "win32")` tasklist liveness-probe tests inside `test_frontend_quality_ui.py` always skip on the CI runner and would falsely trip "any skip → red").
- **Module: docs / long-term experience (`AGENTS.md` + `docs/agent-reference/session-learnings.md`)** — `AGENTS.md` blind-spot 3 corrected MIN-2241's "live case (permanently red)" in place to `[2026-09-24 revision: changed to \r?\n\r?\n]` per the "correct falsified factual statements" exception, keeping the pitfall's general warning…


## v4.3.0-dev (2026-09-24) — Comment streamlining across four `src/` files: source-selection probes / SRT subtitles / sync HTTP / the ttwid credential cache, "cut derivation to conclusions + turn adjacent restatements into cross-references" (comment-only, zero logic change)


### Files involved (grouped by module)

- **Module: source selection / probe subsystem (`src/stream_select.py`)** — 1 file modified, net −11 comment lines:
  - Long function headers cut to conclusions: `_probe_hls_segment` (19→15 — the douyu hw incident shape with `hw3a.douyucdn2.cn` always returning 200 on the playlist while `f19c*.livehwc4.com` segments 404, the hls demuxer "Segment failed too many times, skipping" zero-output cause, the three decision principles, the 401/403-retry vs 403-no-retry adjudication chain and the MID-N32 masking rationale all retained), `_validate_stream_url` (16→14, the five consistency criteria 1)–5) against `async_http.get_response_status` kept item by item), `_confirm_get_ok` (11→9), the MID-2231 "second hop derived from the body" boundary block plus the `_PRIVATE_HOST_PATTERN` header (10→8, the dual-cost reasoning behind "literal matching only, no DNS resolution" kept).
  - The two SEV-N05 blocks inside `select_source_url` re-laid out: the proxy-normalisation block (with the `async_http:255/365`, `room:92/176/268`, `spider:3495` comparison, the `[历史注] sync_http:179` refutation and the `grep` re-verification command) and the "whole round shares one Client + construction failure collapses to `probe_client=None`" block (the three reasons ① ② ③, not writing `_mark_probe_reject`, and the constraint that a new `tr` template must be synced into four catalogues — all kept).
  - Adjacent restatements converted to cross-references: inside `_validate_stream_url` the "same-host probe throttling" and "last-resort pass-through ≠ ffmpeg cannot pull" notes no longer re-narrate the root cause but point at `_PROBE_MIN_HOST_INTERVAL` / `_confirm_get_ok`
  - **One refuted statement corrected in place**: the Range-GET retry comment used to say "retry after `_GET_RECHECK_INTERVAL`" while the code actually calls the jittered `_recheck_delay()` (= baseline + `uniform(0, _GET_RECHECK_JITTER)`)…
- **Module: danmaku subsystem / SRT subtitles (`src/srt_writer.py`)** — 1 file modified, net −5 comment lines:
  - The MIN-2236③ "block-number wrap-around" derivation inside `write()` (4→2) now points at `_open_segment` (which remains the single source of truth for the terminal-state flag), keeping only what is local to that site: "log at debug and never raise, so the collector thread's `on_message` is not polluted".
  - MIN-24① "the throttled re-open must happen before the entry is produced" 6→5 (the `_index=0` / `_last_end=None` reset ordering, the SRT increasing-block-number requirement, and both post-fix outcomes are kept)…
- **Module: sync HTTP client (`src/sync_http.py`)** — 1 file modified, net −10 comment lines:
  - The module header's "security boundary" and "call surface" blocks merged internally (23→17): the F-12 lazy-construction rationale, the `grep -rn "sync_http\|sync_req(" …` forensics command and its three hit categories, `src/weverse_auth.py` (deleted 2026-09-23), the `[历史注]` record refuting "all sync_req call sites live in `src/spider.py`" (SEV-2226), CERT_NONE being unreachable in production, and the two reasons for keeping the module (the F-12 invariant plus the `tests/test_sync_http.py` regression lock) are all still present.
  - SEV-2226 response-cap block 17→13: the reasons why ① chunked compressed-body reading and ② capped decompression output are both indispensable, `MemoryError` being a `BaseException` that the existing `except Exception` cannot catch, "80+ rooms and the web panel share one process", the value-selection policy (prefer over-loose over false kills), and the chain "raise `ValueError` → empty response = not live / suspected risk control" are kept.
  - The proxy branch's "known residual gap" (`response.text` bypassing both caps, the price of each possible fix, and that the 2026-09-23 round only closed the urllib path) 7→6…
  - The stranded comment `# 同步 HTTP 客户端模块 - 提供同步 HTTP 请求功能` (previously drifting after the import block) was moved to the first line as the module header, restoring the "module overview" layer…
- **Module: douyin credential cache (`src/ttwid.py`)** — 1 file modified, net −4 comment lines:
  - The `_ttwid_lock` block (H-2 + why it must stay an `RLock` and never regress to `threading.Lock` or a module-level `asyncio.Lock` singleton + the `tests/test_concurrency.py::test_ttwid_module_pattern` type lock), the H-2 original-implementation block in `get_ttwid` and the MIN-2220 "deliberately clear everything instead of one bucket" block in `invalidate_ttwid` each tightened by 1–2 lines, keeping the deadlock derivation and the cost comparison.
  - `_cache_ttwid` no longer re-narrates why "the mirror takes part in no decision" but points at the module-level `_cached_ttwid_by_proxy` block (the MIN-2220 single source of truth)…
- **Module: this document (recalibrated §12)**: the `src/sync_http.py` subsection used to claim "two openers (insecure / secure) are pre-built according to the SSL verification switch", which no longer matches the implementation after F-12 (only `_opener_secure` is pre-built…


## v4.3.0-dev (2026-09-24) — `main.py` comment streamlining: removed 2 pure function-name / code-restatement noise comments (comment-only, zero logic change)


### Files affected (grouped by module)

- **Module: `main.py` (CLI recording core entry / multi-threaded concurrent recording scheduler)** — 1 file changed, 2 pure-restatement comments removed:
  - First body line of `safe_exit()` (the SIGINT/SIGTERM/SIGBREAK signal handler): `# 安全的退出处理函数` (originally line 541, whole line deleted) — restates the function name and is fully redundant with the function-header comment right above it ("set the exit flag, clean up ffmpeg processes and the HTTP connection pool, then exit") — matches `AGENTS.md`'s "a comment that restates code behavior is noise".
  - Trailing comment on the module-level `os.makedirs(default_path, exist_ok=True)`: `# 确保下载目录存在` (originally line 307) — restates what the call does…
  - Intentionally kept: `# 注册信号处理器` (line 554) before the `signal.signal` block as a lightweight section label; and all numbered / regression-lock "why" comment blocks.


## v4.3.0-dev (2026-09-24) — Repo-wide comment optimization: 3 factual corrections in root/build docs + compression of multi-layer "correction archaeology" across several subsystems (comment-only, zero logic change)


### Files involved (grouped by module)

- **Dependency list / build config (factual corrections + compression)**:
  - `requirements.txt` — fixed 3 falsified statements (verified against source): (1) the `requests` comment "spider / per-platform page fetching / Weverse auth direct call" → in fact `src/spider.py` uses the httpx async path (`async_http`), `src/weverse_auth.py` was deleted on 2026-09-23, and the only real consumers are the ffmpeg / node install-download scripts…
  - `pyproject.toml` — fixed the same-origin `urllib3` disproven statement (aligning both files)…
- **Windows stop script (encoding fidelity + compression)**:
  -  UTF-8 garbles the Chinese prompts; compressed 4 process-matching / silent-mode "correction archaeology" blocks, 485→480 lines.
- **Standalone front-end player**:
  - `index.html` (pure LF) — compressed the `MIN-2241` SRI comment block, keeping every point: pinned-version ≠ pinned-content, not behind web_api CSP/nosniff, fail-closed, crossorigin precondition, sha384 verified across two CDNs, and re-hash on upgrade.
- **Danmaku subsystem (`src/` compression / de-duplication)**:
  - `src/base.py` — `DanmakuBase.__init__` restatement comment 2→1 lines.
  - `src/collector.py` — `DanmakuCollector.__init__` parameter restatement 5→3 lines, keeping the non-obvious `write_srt` / `monitor` / `only_fans` semantics.
  - `src/danmaku_monitor.py` — de-duplicated the "does not go through `get_hub()` to initialize" statement shared by `suspend/resume_monitor_writes` and `close_monitor_file`
  - `src/cookie_cache.py` (LF) — removed the redundant closing sentence at the end of the "cross-module usage" header block (duplicated the background paragraph).
  - `src/config_bool.py` (LF) — compressed the header's background paragraph and the zero-dependency / circular-import rationale (22→19), **fully keeping** the "four inconsistent legacy parsers" evidence block (main.
- **Concurrency / HTTP (`src/`)**:
  - `src/async_http.py` — removed the drift-prone verbatim re-quote of the function signature inside `get_response_status`, keeping the `proxy_addr` alias, the AGENTS "proxy / verify / UA must agree across the sync and async validators" rule, and `get_record_user_agent(platform) or MOBILE_UA`.
  - `src/http_config.py` — compressed the `get_effective_ssl_verify` truth table (7→4), keeping the FFmpeg 9.0 default-verification and http / https mode adjudication.
  - `src/ffmpeg_proc.py` — compressed the MID-32 "fix #2" derivation (ThreadPoolExecutor's non-daemon workers dead-locking on the atexit path, 6→4).
- **ffmpeg install subsystem (`src/`)**:
  - `src/ffmpeg_install.py` (LF) — compressed three blocks: `install_ffmpeg_windows` arch dispatch (9→6), `install_ffmpeg_linux`'s F-17 + MIN-24④ multi-layer archaeology (9→7), and MID-59 (11→9)…
  - `src/ffmpeg_master_download.py` (LF) — compressed the module header's "correct download method ①-⑤" into an overview that points to each function (13→8), keeping the SEV-2222 ID and concrete nouns.
  - `src/log_archive.py` — compressed the `_web_console_rebind_pending` derivation (7→5), keeping every fact: MID-2258 devnull black hole, `_streams_bound_to()` name mismatch, per-round retry, `_archive_lock`.
- **Intentionally unchanged after audit (reference-grade "why" or density near the gate)**: `i18n.py`, `msg_push.py`, `web.py` (root) and `src/config_io.py` — all high-value single-layer "why" comments, and `msg_push.py`'s density is near 13%…


## v4.3.0-dev (2026-09-24) — `src/` comment streamlining: cut derivation to conclusions and removed code-restatement in `recorder_status.py` and `room.py` (comment-only, zero logic change)


### Files touched (classified by module)

- **Module: `src/recorder_status.py` (recording-status snapshot & console display)** — 1 file modified, net removal of 2 comment lines (3 blocks tightened):
  - the MI-10 block in `get_status()`: 4→3 lines, dropping the "the old comment claimed … and so" narrative chain while keeping the dead-logic basis for the 5-retry, the write-site audit (`main.py` recording add/remove / `src/notify.py` counter update) and `with main.record_state_lock`.
  - the MID-31 cadence header for `display_info`: folding the "root cause" clause into parentheses, tightening wording.
  - the trailing finally-cadence comment: 4→3 lines, removing the duplicate restatement of the MID-31 root cause in favour of a cross-reference, keeping only this site's unique `logs/web_console.log` / `ValueError: I/O operation on closed file` detail.
- **Module: `src/room.py` (Douyin room resolver / X-Bogus / sec_user_id)** — 1 file modified, net removal of 4 comment lines (3 blocks tightened):
  - the "2026-09-12 review 6.3" block in `get_xbogus()`: 4→3 lines, compressing the derivation while keeping the `execjs.compile` → `utils.run_js_async` rationale and the `(path, mtime)` cache fact.
  - the "6.3 verify" block in `get_sec_user_id()`: 4→3 lines, keeping the `http_config.ssl_verify` three-AsyncClient consistency criterion and the `sec_user_id / unique_id / web_rid` chain.
  - the MID-2246 fallback-logging block in `get_unique_id()`: 7→5 lines, keeping `except Exception: pass`, the JS anti-scrape shell page, the root-cause enumeration, the AGENTS "no silent exception swallowing" criterion, the debug-vs-warning choice and the `spider.py` reference.
- **Named but intentionally unchanged**: `src/scheduler.py` — the `AGENTS.md` comment-quality reference whose comments are all load-bearing concurrency-semantics / copy-sync anchors…


## v4.3.0-dev (2026-09-24) — Comment refinement across four `src/` files: removed "function-header vs inline" restatements and the same-source `proxy.py` scheme narrative (comment-only, zero logic change)


### Files touched (classified by module)

- **Module: `src/notify.py` (notification & recording-state hooks)** — density 26.4% → 24.6%, net removal of 5 comment lines:
  - `run_script()`: compressed the "2026-09-12 review 6.
  - `record_error()` / `record_success()`: removed the first inline-comment clause ("thread-safely record one error/success .
- **Module: `src/proxy.py` (system-proxy detection)** — density 35.6% → 34.9%, net removal of 3 comment lines:
  - `_split_scheme()` / `_get_proxy_info_linux()`: the causal chain "socks5://.
  - **Text-lock preserved**: the "residual registration" block above `_LINUX_PROXY_ENV_NAMES` (`没有任何生产消费点` / `代理地址` / `main.py`) was kept verbatim and no falsified "authentication proxy fixed" statement was introduced — those three substrings are asserted against the raw source by `tests/test_regression_2026_09_22_net.py::TestMid2233ResidualRegistered`.
- **Module: `src/logger.py` (logging configuration)** — density unchanged at 35.
- **Module: `src/node_install.py` (Node.


## v4.3.0-dev (2026-09-24) — `src/stream.py` comment streamlining: 13 verbose / multi-layer "correction archaeology" blocks cut to conclusions (comment-only, zero logic change)


### Files touched (classified by module)

- **Module: `src/stream.py` (live-stream URL resolution / quality-tier selection & downgrade)** — 1 file modified, 13 comment blocks compressed:
  - Constant headers: `DOUYIN_KEY_TO_CODE` (MID-2229, the archaeology about the pre-fold version only recognising ORIGIN folded into a `[History note]`), `_PLAY_URL_KEY_ORDER` (MID-20, the two-contract description merged), `HUYA_RATIO_TO_CODE` (MID-14, the 1000/250-addition derivation compressed).
  - Utility functions: `_pad_list` (MI-02 + the 2026-09-12 review 6.
  - `get_douyin_stream_url`: the MID-2229 block inside `_sort_quality_items` (literal version only recognises ORIGIN/OD/BD/UHD/HD/SD/LD, real keys all fall to default 99).
  - `get_tiktok_stream_url`: the `_pad_list` block (MI-02), the MID-16 block (keeping `AttributeError` and the `{"url": "", ...}` shape), the MID-15 block (all three ① ② ③ consequences and the "no HLS probe is ever sent" hard semantics kept).
  - `get_kuaishou_stream_url`: the MIN-06 block (numeric-quality two-table misalignment, the `"2"` UHD(2000)-vs-BD30(30000) contrast, the `tests/test_stream.py` and standalone named references kept).
  - `get_huya_stream_url`: the MID-13 block (exsphd set semantics, `labels=[...]` / `reversed(findall(264_\d+))` / `HUYA_RATIO_TO_CODE` all kept), the MID-2228 block (the `len(quality_list) > 1` condition and the three-step arbitration chain).
  - `get_douyu_stream_url`: the MID-68 block (`ast.BinOp` vs `JoinedStr`, the `err_detail` pre-evaluation convention).
  - `get_stream_url`: the MID-20 + SEV-2201 block inside `get_url` (the full `AttributeError: 'str' object has no attribute 'get'`, and the `SOOP/PandaTV/WinkTV/TTingLive/TwitCasting/Twitch/百度直播/ShowRoom` platform list kept verbatim).


## v4.3.0-dev (2026-09-24) — `gui.py` comment de-duplication: merged 3 "method-header vs first-body-line" restatements (comment-only, zero logic change)


### Files touched (classified by module)

- **Module: `gui.py` (GUI main-window entry)** — 1 file modified, 3 redundant comment lines removed:
  - `SystemTray.run()`: removed the first body line "启动系统托盘图标（阻塞运行；Windows / Linux 专用，由后台线程调用）。" — it duplicated the method header "在后台线程启动托盘图标（Windows / Linux 阻塞运行，macOS 禁用）"
  - `LiveRecorderGUI._log()`: collapsed two body lines "添加日志到队列（线程安全）。本方法不触碰任何 Tk 对象， / 可在任意线程调用…" into one, keeping only the incremental info not covered by the header (callable from any thread…
  - `LiveRecorderGUI._cleanup_zombie_ffmpeg()`: removed the first body line "清理录制子进程（main.
- **Hit by de-dup but kept**: `LiveRecorderGUI._shutdown_and_quit()`'s first body line "…（由其清理 ffmpeg）→ 超时整树强杀 → 兜底清理" encodes the execution order shared with the stop path, so it is not a pure restatement and was left unchanged.


## v4.3.0-dev (2026-09-24) — Type-stub completion: cleared mypy `disallow_untyped_defs` errors across 7 `.pyi` files in `typings/execjs/` (IDE no longer reports `no-untyped-def` when a single file is opened)


### Files touched (classified by module)

- **Module: `typings/execjs/` (third-party PyExecJS type stubs)** — 7 `.pyi` files modified:
  - `_runtimes.pyi`: `register(name: str, runtime: Any) -> None`, `get(name: str | None = ...) -> Any`; module variable `_runtimes: dict[str, Any]`.
  - `_exceptions.pyi`: `ProcessExitedWithNonZeroStatus.__init__(status: int, stdout: str, stderr: str)`.
  - `_abstract_runtime.pyi`: `exec_ -> str` / `eval -> Any` / `compile -> AbstractRuntimeContext` / `is_available -> bool`
  - `_abstract_runtime_context.pyi`: `exec_ -> str` / `eval -> Any` / `call(name: str, *args: Any) -> Any` / `is_available -> bool`; added `from typing import Any`.
  - `__main__.pyi`: filled parameters and `-> None` for `PrintRuntimes.__init__` and `__call__`; added `from typing import Any`.
  - `_pyv8runtime.pyi`: `Context.__init__(source: str | None = ...)`, `convert(cls, obj: Any)`.
  - `_external_runtime.pyi`: `ExternalRuntime.__init__(name: str, command: list[str], runner_source: str, encoding: str = ..., tempfile: bool = ...)`, `Context.__init__(runtime: ExternalRuntime, source/cwd: str = ..., tempfile: Any = ...)`, `Context.is_available -> bool`.
- **Scanned, no change needed**: `typings/customtkinter/__init__.pyi`, `typings/pystray/__init__.pyi` (every function in both packages already carries complete parameter/return annotations…


## v4.3.0-dev (2026-09-22) — Metadata source-of-truth sync + full quality-gate run + four-catalogue i18n verification (zero production-code change)


### 1. Changes by module

| Module path | Change type | What changed | How verified |
| --- | --- | --- | --- |
| `DouyinLiveRecorder.egg-info/` | **Metadata rebuild** | Regenerated via setuptools `egg_info`, closing two drifts against `pyproject.toml`: in `requires.txt` / `PKG-INFO` the `starlette` lower bound `1.0.1 → 1.3.1` and the `protobuf` lower bound `6.31.1 → 6.33.5` (upper bound `<8` kept, F-14); `SOURCES.txt` picked up 6 new test files (`test_config_io_update_file`, `test_node_install`, `test_platform_danmaku_offline`, `test_spider_hardening`, `test_video_postprocess_paths`, `test_web_tray`); version stays 4.3.0 and `PKG-INFO` is unchanged at 1401 lines | `scripts/check_version.py` PASS; all 21 entries match one-to-one across `pyproject [project.dependencies]` / `requirements.txt` / `requires.txt` (the only difference is setuptools normalising `protobuf>=6.33.5,<8` to `protobuf<8,>=6.33.5`, which is not substantive) |
| `config/config.ini` | Config key added | `[Web]` now carries `web_allowed_hosts`. Introduced by MID-36 (DNS-rebinding defence), it previously existed only in `src/web_config.py::WEB_DEFAULTS` — never written to disk and absent from every config document, so new users could not discover it until the "fill in missing key" path ran | configparser parses it cleanly (BOM preserved); `[Web]` grew from 8 to 9 keys |
| `README.md` / `README_EN.md` | Docs synced | The `[Web]` config block now lists `web_allowed_hosts` with a description (when to set it, what happens otherwise) in both languages | Both README sections correspond item by item |
| `CODE_WIKI.md` / `CODE_WIKI_EN.md` | Docs synced | A `web_allowed_hosts` row was added to the Web config table, stating the real decision rule of `src/web_config.py::is_host_allowed` (IP literals and dot-less single-label names pass implicitly; multi-label domains must be registered explicitly; `web_host` bound to `0.0.0.0`/`::` is not added to the allowlist) | Written after reading `is_host_allowed` back at source |
| `.gitignore` / `.dockerignore` / `pyproject.toml` (five sections: `[tool.black]`, `[tool.isort]`, `[tool.mypy]`, `[tool.coverage.run]`, `[tool.basedpyright]`) / `.coveragerc-concurrency` | **Same-source lists completed** | Added `.qoder-credits/` — a third-party coding-agent output directory that was the only root-level directory neither Git-ignored, nor excluded from the Docker build context, nor skipped by tooling. All eight lists now agree with the existing 14 local-tool directories | `black --check .` and `isort --check-only .` both exit 0; per-token comparison across the eight lists shows no gaps |
| `AGENTS.md` | Regression guards | Two new entries under "Type checking, comments and static gates": ① **grep every call site before deleting a module-level function or constant** (including how `and` short-circuiting turns it into a delayed `NameError`); ② **forwarding test stubs must annotate `*args`/`**kwargs` as `Any`** (with `object`, only basedpyright reports `reportArgumentType`; mypy stays silent) | Both originated from findings in this round |
| `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` | Recompiled | 664 entries (including the gettext header empty msgid), 85 544 bytes; `--check` passes both before and after, i.e. `.po` and `.mo` were already in sync and recompilation added no content delta | `scripts/compile_po.py --check` |


## v4.3.0-dev (2026-09-21) — Full worktree change ledger (by module): `CODE_REVIEW_2026-09-21` remediation round + coverage work stream


### Batch B: landed changes, grouped by module

| Module path | Report ID | Change | Companion tests |
| --- | --- | --- | --- |
| `src/spider.py` | **SEV-N02** | A refreshed PopkonTV token already carried the `Bearer ` prefix when persisted to disk, and it was prefixed again on read-back → double prefix, credential reuse silently broken; normalised on the write side | `tests/test_spider_platforms.py` |
| `src/spider.py` | **SEV-N04** | Taobao replaced the user's whole Cookie with the response `Set-Cookie` and persisted it back into `config.ini`, destroying the login state silently | `tests/test_spider_hardening.py` |
| `src/spider.py` | MID-48 (a 09-20 report item, executed in this day's domestic/overseas batches) | Converged the “bare JSON extraction + decorator fallback” pattern in the platform parsing layer: `_loads_dict` replaces bare `json.loads`, deep chained indexing goes through the `_dig` safe descent (a WAF/interstitial HTML page no longer raises `JSONDecodeError`) | existing spider cases |
| `src/web_api.py` | **SEV-N03** | The “non-loopback bind + no auth” panel invariant could be bypassed by two sequential PUT requests, because the judgement baseline `web_host` was itself writable through the API. Security judgements now uniformly read `_guard_bind_host(app, …)` = the **address the process actually bound**, and the 403 text is consolidated into `_insecure_bind_detail(action, bind_host)` | `tests/test_web_api.py` |
| `src/web_api.py` | MID-N42 | Origin and Host are **two separate allow-lists**: Host keeps using `web_config.is_host_allowed`, Origin is judged independently; port and address are now judged together (`web_port` is likewise an API-writable config value) | `tests/test_web_api.py`, `tests/test_web_config.py` |
| `web.py` | **SEV-N03** (same item) | At startup, pass **the address and port this process actually binds** into the app state as the single source for security judgements (no longer re-reading the config value) | same `tests/test_web_api.py` |
| `src/web_config.py` | MID-N45 | Added an “outbound target” clamp: push endpoint URLs / ntfy address / proxy address / SMTP and other URL-typed keys inside the allow-list are all validated; extracted the shared core `_validate_room_url_target` and added an `allow_local_targets` exemption (admitting only loopback plus RFC1918/ULA, i.e. “the user's own network”); the escape hatch deliberately does **not** reuse `DOUYIN_WEB_ALLOW_INSECURE` | `tests/test_web_config.py` |
| `src/stream_select.py` | MID-N32 | Playlist / segment / same-origin FLV fallback URLs are all signed direct links whose probe logs were previously unredacted; probe logging in this file is now uniformly redacted | `tests/test_stream_select.py` |
| `src/config_io.py` | MID-N57 | Backup redaction previously wired only the `is_sensitive_item` predicate and missed the panel-side “section allow-list + key-name regex” criterion, leaving an under-redaction surface; it now applies both predicates | `tests/test_config_io_backup.py` |
| `src/javascript/haixiu.js` | MIN-N39 | Real-shaped captured samples in the trailing comments were replaced with `<REDACTED>` placeholders; removed the dead `bnu` / `bn` methods that referenced jQuery `$` (**comment/dead-code level only — the signing chain `bsq→pf→as→brm→cls→pt` is untouched**) | covered by `check_runtime_pins.py` / `_JS_SHA256_EXPECTED` |
| `src/utils.py` | MIN-N39 | Recomputed two pinned hashes in `_JS_SHA256_EXPECTED` (`haixiu.js` and `migu.js`; old values `e8f13f4a…` / `01bf22bd…` retired); the table comment now states “these 5 entries are every script in use” with the measured basis | same `tests/test_utils.py` |
| `CODE_REVIEW_2026-09-21.md` | — | **New document** (540-line full-source review report, grouped as 6 P0 / 74 P1 items); it is this batch's input source | n/a |


## v4.1.0-dev (2026-09-10) — 28 code-review fixes + repository metadata sync + four-language catalog completion (521 → 539 entries)


### 1. Code-review fixes (by module)

- **`main.py`**:
  - The ffmpeg flags `-reconnect_delay_max 60 / -reconnect_streamed / -reconnect_at_eof` were moved from **after** `-i` to **before** `-i`: `-reconnect*` are input-level options…
  - `_rec_sem.acquire()` was moved from **after** `Popen` to **before** it, and the "Popen → register → danmaku start → loop" sequence is now wrapped in a single `try/finally: _rec_sem.release()`, eliminating the permanent semaphore leak on startup exceptions that depressed the concurrency ceiling for later recordings.
  - `process.wait(timeout=30)`'s `except Exception: pass` was changed to `except subprocess.TimeoutExpired:` followed by `kill()` + re-`wait()`
- **`src/ffmpeg_proc.py`**: `_cleanup_single_ffmpeg_process` / `cleanup_all_ffmpeg_processes` now check the return value — on failure they warn and only remove entries whose `poll() is None`, keeping survivors (no longer blindly dropping registry entries).
- **`src/stream_select.py`**: the exception branch now does `if last_resort: warning; return True`, matching the stable-reject `last_resort` pass-through above.
- **`src/web_config.py`**: added `is_sensitive_key()` / `is_sensitive_item()` (regex `令牌|密码|授权码|token|secret|passwd|password|api[_-]?key`, case-insensitive…
- **`web/app.js`**: added the JS equivalent `isSensitiveField(section,key)`
- **`src/collector.py`**: cached `self._cls_name`
- **`src/srt_writer.py`**: added `_sanitize_srt_text()` (`\r\n→space`, `-->→->`)…
- **`src/spider.py`**: added `import os` and `_read_haixiu_token_override(is_haixiu)`, reading the access token via "env `HAIXIU_ACCESS_TOKEN`/`HAIHAI_ACCESS_TOKEN` → `config.ini [Cookie]` → built-in fallback", removing the hardcoded token.
- **`src/ttwid.py`**: on a non-blocking acquire failure it now re-acquires in blocking mode (serial takeover) instead of fetching outside the lock, avoiding duplicated concurrent fetches.
- **`src/async_http.py` / `src/sync_http.py`**: the request-body check `if data or json_data:` was changed to `if data is not None or json_data is not None:` (an empty dict is a valid body…
- **`src/danmaku_monitor.py`**: `setdefault` replaced with explicit `get` + on-demand creation (stops evaluating the default-arg factory on every message, removing noise).
- **`src/cookie_cache.py` / `src/async_http.py`**: logs now pass through `utils.mask_credentials()`.
- **`src/utils.py`**: added `mask_credentials(text)` — regex strips proxy credentials (`://user@`) and Secret query params (`signature|token|access_token|apikey|api_key|secret|key|x-bogus|a-bogus|ms_token|nonce|sid`, etc.
- **`scripts/check_coverage.py`**: `missing_modules` now returns `1` instead of warning (gate no longer "falsely green").
- **`scripts/smoke_test.py`**: `load_config` raises `ValueError` on an invalid top-level structure; `main()` catches `(OSError, ValueError)` → `sys.exit(2)`.
- **`scripts/compile_po.py`**: added `import os`; writes now go to a temp file + `os.replace` for atomic replacement (avoids leaving a truncated `.mo` on mid-write failure).
- **`scripts/check_version.py`**: `strip_v` changed from `lstrip("v")` to `removeprefix("v")` (avoids accidentally stripping prefixes like `ver`).
- **`tests/`**:
  - `test_concurrency_rate_limit.py` fully rewritten to drive the real `src.ttwid.get_ttwid()` (8 threads assert `_fetch_ttwid` is called only once) + `src.stream_select._throttle_probe()`, killing the "re-implement logic then assert, passes even if src/ is deleted" false-green.
  - `test_record_container.py`: `_segment_format_nodes(path=_MAIN_PATH)` gained a `path` parameter; added `TestSegmentFormatSecondDefinitionPoint` covering `src/video_postprocess.py`.
  - `test_danmaku_wiring.py`: `monkeypatch.setattr(main.time, "sleep", ...)` replaced with a `SimpleNamespace` shim overriding only `sleep` (avoids polluting the global `time` module).
  - `test_async_http.py`: added `call_args.kwargs["data"]`/`["content"]` assertions.
  - Deleted `tests/test_utils.py.isorted` (isort residue).


## v4.1.0-dev (2026-09-10) — 8 product-decision items + 4 machine-validation items + uv.lock aligned to 4.1.0 (v4.1.0 second batch)


### I. 8 product-decision items (by module)

- **`index.html`**: `hls.js@latest` → pinned `hls.js@1.7.2` (jsdelivr CDN supply-chain risk; aligns with `flv.js@1.6.2` pinning convention in the same file).
- **`src/http_config.py` + `main.py`**: TLS verification split into a stream-fetch-only path (`get_effective_ssl_verify`) and a control-plane general path (`ssl_verify`)…
- **`main.py`**: Audio branch `SEGMENT_FORMAT_BY_SUFFIX` aligned with extension/encoder — pure-audio platforms (MaoeFM/Look etc.
- **`src/notify.py`**: `run_script` now uses `communicate(timeout=_SCRIPT_TIMEOUT_SECONDS=300.0)` with `process.kill()` + secondary `communicate()` on timeout, preventing third-party scripts from blocking the calling thread indefinitely.
- **`src/web_api.py`**: Three real auth-model hardening items — ① middleware uniformly adds `X-Content-Type-Options: nosniff` + `X-Frame-Options: DENY` (both allow and deny paths…
- **`gui_legacy.py` deleted + metadata sync**: Deleted root `gui_legacy.py` (functionally redundant with `gui.py` and carrying a `CREATE_NO_WINDOW` child-process bug that silently disabled `send_signal(CTRL_BREAK_EVENT)`)…
- **`src/collector.py`**: Decoupled danmaku SRT disk-write from the event-loop thread — `_on_message` only does O(1) `queue.SimpleQueue.put`, an independent daemon thread `_srt_writer_loop` consumes `(user, msg, now)` tuples and calls `srt.write` (now captured on the event-loop side so the timeline is unaffected by writer-thread scheduling delay).
- **`i18n.py` + 18 call sites**: New `tr(template, **kwargs)` helper — `_tr(template)` lookup first, then `.format(**kwargs)` for second-pass interpolation.

> **The pre-existing 200+ parameterized logs still use the f-string form** (historical technical debt, not in this batch's scope); a future "full i18n parameterized migration" project will replace them.


### II. 4 machine-validation items (conservative implementation, by module)

- **`src/spider.py`**: New `_safe_loads(text) -> Optional[dict]` exception-safe parser (catches `JSONDecodeError`, logs a warning, returns `None`) and `_is_safe_http_url(url)` URL scheme whitelist (only allow `http`/`https`/`ws`/`wss`
- **`src/ws_client.py`**: `_heartbeat_loop` adds `asyncio.wait_for` guard (timeout = `heartbeat_interval + 1.0`)…
- **`src/proxy.py`**: `ProxyInfo.__post_init__` now accepts IPv6 literals — `[::1]:8080` (the typical IPv6 form in Windows registry `ProxyServer` values) is recognized explicitly…
- **`src/video_postprocess.py`**: `segment_video` / `converts_mp4` / `converts_m4a` (the three `_run_ffmpeg_checked` callers) each add an independent `except subprocess.TimeoutExpired as e:` branch with a classified error message ("segmentation timed out" / "transcode timed out" / "audio extraction timed out") — instead of being swallowed by `except Exception` as "unknown error", which lost the "ffmpeg hung" semantic.
- **`tests/test_machine_validation_fixes.py` adds 7 tests**: ① `_safe_loads` valid/non-dict/garbled JSON paths…


## v4.0.9.4-dev (2026-09-06) — Eight-file repository metadata sync + i18n catalog completion (516 → 521 entries) + this cycle's change overview (classified by module)


### 3. This Cycle's Code Changes (Classified by Module, 2026-09-02 ~ 09-06)

- **`main.py`**: new global `hls_collection_exclude_platforms` plus main-loop parsing (supports Chinese/English comma separators, hot-reloaded each round)…
- **`src/stream_select.py`**: `select_source_url` gained the effective switch `hls_effective_enabled = main.hls_collection_enabled and not hls_excluded` (excluded platforms drop the whole HLS candidate group instead of reordering it).
- **`src/spider.py`**: `extract_douyin_hevc_flv_url()` now appends `&codec=h265` (returns as-is if already present), fixing missed detection in `_is_h265()` and the h265 fallback logic.
- **`src/async_http.py`**: removed the cross-loop `run_coroutine_threadsafe(client.aclose(), ...)` branch (root fix for the flaky "FakeAsyncClient.aclose was never awaited" warning).
- **`src/web_config.py`**: added `BUILTIN_QUALITIES` (aligned with `stream_select.get_quality_code`
- **`src/web_api.py`**: added `GET /api/rooms/qualities` and `PUT /api/rooms/qualities` (option add/remove) plus `PUT /api/rooms/quality` with `RoomQualityUpdate` (per-room quality change, sharing `update_room_quality` with the GUI).
- **`gui.py`**: added `_refresh_quality_context` / `_anchor_url_map` / `_anchor_quality_map` / `_quality_menu_values` / `_on_room_quality_change`, plus a 6th "Switch quality" column (`CTkOptionMenu`) in the quality monitor…
- **`web/index.html` / `web/app.js` / `web/style.css`**: quality dropdown became a backend-driven add/remove option list (chips panel)…
- **`scripts/`**: `douyin_live_recorder_standalone.py` moved in from the repo root with `find_ffmpeg()` fixed (script dir → repo root → PATH)…
- **`tests/`**: new `test_record_container.py` (13 cases incl.
- **Repo-wide comment completion** (2026-09-03): 41 files / +1370 lines, proven logic-neutral by `ast.dump` equivalence.


## v4.0.9.3-dev (2026-09-02) — Standalone single-file integration (standalone) type-annotation fixes (mypy: 4 errors cleared)


### Files Involved (Classified by Module)

**1. Type-annotation fixes (modification) — `douyin_live_recorder_standalone.py`**

- L265 `_fetch_json`: the return `json.loads(resp.text)` was typed `Any` by mypy (declared `dict[str, Any]`) → changed to `cast(dict[str, Any], json.loads(resp.text))`.
- L751 `_douyu_sign`: the return `json.loads(out.stdout.strip())` was typed `Any` (declared `dict[str, str] | None`) → first guard with `isinstance(sign, dict)` (returns `None` when not a dict), then `cast(dict[str, str], sign)`, eliminating a non-dict runtime crash.
- L853 `dispatch`: `fn(url, proxy=proxy, cookies=cookies)` keyword call raised mypy "Unexpected keyword argument 'proxy'/'cookies'" — root cause: `PLATFORM_RULES` used `Callable[[str, str | None, str], StreamInfo`, whose alias drops parameter names so only positional passing type-checks.
- `typing` import: `from typing import Any, Callable` → `from typing import Any, Protocol, cast` (removed the now-unreferenced `Callable`).


## v4.0.9.2-dev (2026-08-29) — Full Working-Tree Change Overview (Classified by Module): 97 files / +10659 −3138, covering all uncommitted changes from 2026-08-23 through 08-29


### Files Involved (Classified by Module)

**1. Concurrency Scheduling & Recording-Engine Core (new feature + modification) — `src/scheduler.py` (new) / `main.py` / `src/notify.py` / `src/recorder_status.py`**

- `src/scheduler.py` (**new file, 442 lines**): `ResizableSemaphore` (runtime-resizable semaphore, capacity may be 0, growing wakes waiters) / `PlatformBreaker` (per-host circuit breaker closed→open→half-open, probe carries a 60s lease that self-heals to prevent permanent tripping) / `ConcurrencyScheduler` (dynamic scaling default min=8/max=128, fixed-concurrency dual mode, incremental global error-window counting, `adjust_loop` 5s daemon loop) / `host_of` (breaker key extraction).
- `main.py` (+922/−796, the largest single-file change): ① scheduler wiring — `scheduler` instantiated on the first `main()` round, `semaphore`/`recording_semaphore` rebound to its internal semaphores, `set_configured_limit`/`set_recording_limit`/`set_dynamic_mode`/`set_active_count` hot-updated every round…
- `src/notify.py` (+39/−30): `record_error`/`record_success` gain a `key` parameter and delegate to the scheduler (per-key breaking + global backpressure)…
- `src/recorder_status.py` (+20/−2): status JSON gains a `recording_enabled` field…
- **Deletions**: the old `adjust_max_request` `threading.Semaphore` rebuild logic, the unconditional end-of-round `record_success` in `check_subprocess`, and the module-level `threading.Semaphore(1)` in main.

**2. Source Selection & Stream-URL Validation (modification) — `src/stream_select.py` / `src/stream.py`**

- `src/stream_select.py` (+260/−131): ① unified candidate sequence — HLS/FLV/record_url merged into a single ordered sequence validated candidate-by-candidate (Huya flipped to FLV-first via `_FLV_FIRST_PLATFORMS`), h265 candidates removed at sequence construction, `last_resort` unified as "last of the filtered sequence with no record_url"
- `src/stream.py` (+202/−18): the fine-grained Blu-ray tier specialization — `QUALITY_MAPPING_BIT`/`QUALITY_LEVEL`/`QUALITY_CODE_TO_ZH` expanded to 10 items, new `BD_SUB_TIERS`/`HUYA_FIXED_TIERS`/`HUYA_RATIO_TO_CODE`/`DOUYU_RATE_BY_CODE`/`DOUYU_RATE_TO_CODE`/`DOUYU_RATE_DESC`, `get_quality_index` folding sub-tiers into BD, `get_huya_stream_url` ratio-based tier selection with nearest-downgrade, and `get_douyu_stream_url` rate retry chain (up to 2 fallback tiers) with the real tier read back from the `rate` field.
- **Deletions**: the old `DOUYU video_quality_options`/`rate_to_code` tables, the old "FLV is h265 → immediately retry the whole HLS group" inserted fallback, and the `sv=10010` local concatenation (see 3).

**3. Platform Parsers & JS Signing (modification) — `src/spider.py` / `src/javascript/migu.js` (rewritten) / `src/platforms/bilibili.py` / `src/platforms/douyu.py`**

- `src/javascript/migu.js` (+159/−74, full rewrite): adapted to the migu player v_20260731+ wasm interface (import functions 3→12, a.
- `src/spider.py` (+18/−12): `_BANDWIDTH_PATTERN`/`_DOUYIN_HEVC_FLV_PATTERN` hoisted to module-level precompiled regexes…
- `src/platforms/bilibili.py` / `src/platforms/douyu.py`: danmaku color parsing `except` comma-style (PEP 758 mechanical reformat).

**4. HTTP & Network Layer (modification) — `src/async_http.py` / `src/sync_http.py` / `src/http_config.py` / `src/ws_client.py` / `src/ttwid.py` / `src/collector.py`**

- `src/async_http.py` (+15/−2): `close_all_clients_sync` adapted to Python 3.
- `src/sync_http.py` (+21/−2): `_session()` reuses `requests.Session` per thread via `threading.local()` (all ~125 `sync_req` call sites go through it; measured 11.9ms→1.47ms per request).
- `src/http_config.py` (+14/−9): FFmpeg 9.
- `src/ws_client.py` / `src/ttwid.py` / `src/collector.py`: PEP 758 formatting (the danmaku WS `proxy=None` direct-connect convention unchanged).

**5. Config, Logging & Utilities (modification) — `src/config_io.py` / `src/web_config.py` / `src/logger.py` / `src/ffmpeg_install.py` / `src/utils.py`**

- `src/config_io.py` (+17/−2): `read_config_value` default-value write-back now fully serializes into an in-memory `StringIO` first and only touches disk on success…
- `src/web_config.py` (+50/−6): `update_config_line` key matching is now case-insensitive (`_key_line_pattern` precompiled via `lru_cache(128)`)…
- `src/logger.py` (+35/−3): `sys.stderr is None` guard (root-causes the import-time silent crash under pythonw / `console=False` frozen executables)…
- `src/ffmpeg_install.py` (+8/−8): Lanzou-cloud FFmpeg download-source domain switch `wweb.lanzouv.com` → `wwasx.lanzout.com` (Origin/Referer/API and extraction password updated together).
- `src/utils.py` (+23/−18): `_EMOJI_PATTERN` hoisted to a module-level precompiled regex (`remove_emojis` no longer recompiles the ~400-char pattern per call).

**6. Web Panel (new feature + modification) — `src/web_api.py` / `web.py` / `web/index.html` / `web/app.js` / `web/style.css`**

- `src/web_api.py` (+49): new `POST /api/recording/toggle` (recording master switch) and `GET/PUT /api/language` (language query / hot switch: normalized validation → `update_config_line` write-back, falling back to `append_config_line` key creation → `set_language` hot swap)…
- `web.py` (+15/−2): sets `main.recording_enabled = False` before starting the engine thread (Web does not auto-record)…
- `web/index.html` (+54/−41): new "recording control" block (state twin spans + start/stop buttons) and a topbar language selector…
- `web/app.js` (+323/−45): new front-end i18n dictionary `I18N` (~230 lines, ~95 keys × 4 languages) with `t()`/`applyTranslations()`/`initLanguage()` (localStorage memory + backend sync)…
- `web/style.css` (+41/−1): recording-control styles (primary start / red stop / disabled states).

**7. GUI (new feature + modification) — `gui.py` (+173/−7)**

- Crash observability: new `_install_crash_sink()` (`sys.excepthook` + `threading.excepthook` dumping to a temp-dir log with a best-effort dialog, fixing the windowless silent crash under pythonw / frozen executables), `_bootstrap_error_sink()` (`main()` top-level fallback), and the `_bootstrap_crash_reported` duplicate-suppression flag.
- Language menu: a sidebar "语言 Language" `CTkOptionMenu`
- UI callback exceptions changed from `traceback.print_exc()` (which would crash again when `sys.stderr is None`) to in-app logging.

**8. i18n Localization System (new feature + modification) — `i18n.py` (rewritten) / `i18n/en_US.json` (new) / `i18n/en_GB.json` (new) / `i18n/zh_TW.yaml` (new) / `i18n/zh_CN.po|.mo` / `scripts/extract_i18n_strings.py` (new) / `scripts/compile_po.py`**

- `i18n.py` (+270/−31): rewritten as a multi-format engine — per language it probes gettext `.mo` → `<lang>.json` → `<lang>.yaml` in order…
- Catalogs: new `i18n/en_US.json`, `i18n/en_GB.json` (American/British spelling split), `i18n/zh_TW.yaml`
- New `scripts/extract_i18n_strings.py` (166 lines): AST-scans print constant strings + logger f-string templates and diffs them against the four catalogs (f-string normalization: drop format/conversion specs, double→single quotes, pure-placeholder templates excluded).
- `scripts/compile_po.py`: pure-Python po→mo compilation fixed (its own earlier syntax error meant `.mo` was never written); `scripts/check_coverage.py` minor adjustments.

**9.

- `pyproject.toml`: version `4.0.8.3` → `4.0.9.2`
- `requirements.txt`: adds `PyYAML>=6.0.3` (lower bound consistent with pyproject); danmaku dependency comment paths corrected (`src/danmaku/` → actual `src/` layout).
- `uv.lock`: re-locked against the 3.
- `Dockerfile`: base image `python:3.13-slim` → `python:3.14-slim`; Node.js `setup_22.x` → `setup_24.x` (24 LTS, verified against all JS signing scripts plus the rewritten migu.js).
- `docker-compose.yaml`: version example comment synced to 4.0.9.2.
- `build_exe.py`: PEP 758 formatting (packaging/smoke semantics unchanged).
- `.github/workflows/ci.yml`: restructured into a setup + static/typecheck/test/concurrency-test/integration-verify/build-verify/ci-summary topology (explicit per-job timeouts, ci-summary as the sole required check)…
- `.github/workflows/build-release.yml`: `python_build` 3.
- New `.github/actions/retry/action.yml` (linear-backoff ×3 composite action, shared by 9 sites in ci.
- New `.coveragerc-concurrency` (coverage config dedicated to concurrency tests, referenced by CI via `COVERAGE_RCFILE`)…
- **Deletions**: 13 inline `for i in 1 2 3` retry loops across the two workflows, and the build-release.yml debug step.

**10. Tests (4 new files + 30 modified) — `tests/`**

- New: `tests/test_scheduler.py` (192 lines, 16 cases: capacity adaptation / dual-mode switching / `ResizableSemaphore` resizing / breaker state machine and probe lease), `tests/test_record_failure_feedback.py` (311 lines: success / fast failure / slow failure / missing `-i` tolerance / no sampling on stop interrupts / capacity display fallback), `tests/test_quality_tiers.py` (270 lines, 29 cases: sub-tier mapping / index folding / Huya nearest-downgrade / Douyu retry chain), `tests/test_logger_console_sink.py` (72 lines: stderr guard + sink rebuild).
- Modified (representative): `tests/test_stream_select.py` (+215: unified candidate sequence / last-resort pass-through / cross-round backoff hit / no-op for non-whitelisted platforms), `tests/test_i18n.py` (+234: four-catalog consistency / platform gating / C-POSIX filtering / monkeypatch compliance), `tests/test_config_io_readonly.py` (+134: StringIO pre-serialization / bad-key rollback), `tests/test_web_api.py` (+133: language endpoints / recording toggle endpoint), `tests/test_spider_platform.py`, `tests/test_main_fixes.py`, `tests/test_concurrency.py` (lock-type assertions synced), etc.
- Current suite status: `pytest` **786 passed, 2 skipped** (0 failures)…

**11. Documentation & Review Artifacts (new + modified) — `AGENTS.md` / `README.md` / `CODE_WIKI.md` / `CODE_WIKI_EN.md` (new) / `README_EN.md` (new) / `PERF_REVIEW_2026-08-28.md` (untracked)**

- `AGENTS.md` (+270): consolidates the "Concurrency & Thread Model" (scheduling hub / recording-result feedback / lock conventions) and a dozen-plus "Known Pitfalls (Regression Avoidance)" entries (danmaku `proxy=None`, probe tolerance semantics, Huya backoff & FLV-first, UA parity, PEP 758, 3.
- `README.md` (+303): user documentation updated for the 3.
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`: a dozen-plus per-feature changelog entries added since 2026-08-23 plus this overview entry (ZH/EN synchronized).
- `PERF_REVIEW_2026-08-28.md` (untracked, local working-tree file): the full review report behind the P1~P5 performance optimizations (including one misjudgment and its rollback), with conclusions already distilled into AGENTS.
- Erratum: the `docs/web-recording-control-changelog.md` and `docs/security-triage-2026-08-29.md` mentioned by the earlier "Web Panel Manual Recording Control" entry are not present in the current working tree…

**Change Notes**:

- **Complete change-type inventory** — new features (scheduler, Web recording control, fine-grained quality tiers, i18n system, GUI crash fallback/language menu, retry composite action, community templates, three English/bilingual documents, 4 new test files)…
- **Three main lines are mutually independent yet interlocking**: concurrency scheduling (who may issue network requests) → recording feedback (results feed breaker statistics) → probe backoff (bad routes short-listed)…
- **The Python 3.
- This overview complements the individual entries: those explain "why and how", this one explains "which files changed and which module they belong to"


## v4.0.9.2-dev (2026-08-29) — Huya/Douyu Quality-Tier Specialization (Fine-grained Blu-ray Tier Enumeration + User Tier Selection + Unavailable Downgrade Fallback + Cross-Platform Compatibility)


### Files Involved (Classified by Module)

**1. Quality codes & tier tables (new feature — enumeration/labels/downgrade judgment) — `src/stream.py`**

- New module-level `from loguru import logger` (used for selection-downgrade logging).
- `QUALITY_MAPPING_BIT` (L203): appends `BD30:30000`/`BD20:20000`/`BD8:8000`/`BD4:4000` (bitrate ceiling kbps) on top of the base 6 items.
- `QUALITY_LEVEL` (L214): extended to `OD/BD(0) > BD30(1) > BD20(2) > BD8(3) > BD4(4) > UHD(5) > HD(6) > SD(7) > LD(8)`, where larger number = lower quality, used by `is_downgrade` to judge downgrade direction.
- `QUALITY_CODE_TO_ZH` (L222): appends `BD30→蓝光30M`/`BD20→蓝光20M`/`BD8→蓝光8M`/`BD4→蓝光4M`.
- `BD_SUB_TIERS` (L232): `frozenset({"BD30","BD20","BD8","BD4"})`, the Blu-ray sub-tier set (excluded from the generic index mapping).
- Inline measured data (L236-247): under the chuhe room `bitRate=30000`, each ratio's measured resolution/fps — Origin 2560×1440@60fps, BD30M/BD20M/BD8M all 1920×1080@60fps, BD4M 1920×1080@30fps, Ultra 1280×720@30fps, Smooth 800×450@24fps.
- `HUYA_FIXED_TIERS` (L248): `(("BD30",30000),("BD20",20000),("BD8",8000),("BD4",4000))`; `HUYA_RATIO_TO_CODE` (L250): ratio-string → code read-back table.
- Douyu tier tables (L268-293): `DOUYU_RATE_BY_CODE` (request code → rate, incl.
- `get_quality_index` (L335): folds Blu-ray sub-tiers into the `BD` slot (`if quality_str in BD_SUB_TIERS: quality_str = "BD"`), preserving the digit-input 0–5 semantics of index-based selection platforms like Douyin/TikTok.

**2. Huya selection implementation (modified — fine-grained tiers + nearest downgrade) — `src/stream.py::get_huya_stream_url`**

- Parse `gameLiveInfo.bitRate` into `max_ratio` (with `except TypeError, ValueError` tolerance — the legal py314 PEP 758 form)…
- When the requested tier is in `BD_SUB_TIERS` (L~627): take the fixed `target_ratio` from `HUYA_FIXED_TIERS`

**3. Douyu selection implementation (modified — rate mapping + restricted downgrade retry chain) — `src/stream.py::get_douyu_stream_url`**

- The old `video_quality_options`/`rate_to_code` tables are removed in favor of `DOUYU_RATE_BY_CODE` (L~756)…
- Downgrade chain (L~765): along the total order `order = ["0", *DOUYU_RATE_DESC]`, take the requested tier plus up to 2 lower tiers and retry `get_douyu_stream_data` in turn…
- `actual_quality` is now read back via `DOUYU_RATE_TO_CODE.get(actual_rate, ...)` to reflect the server's real issued tier (the `rate` field reflects the nearest clamp, e.g. 8200→4→BD4).

**4. Chinese-name mapping & config/integration whitelist (modified)**

- `src/stream_select.py::get_quality_code` (L57): `quality_zh_to_en` extended to 10 items, adding `蓝光30M/20M/8M/4M → BD30/BD20/BD8/BD4`; unknown quality still falls back to `OD`.
- `src/web_config.py::QUALITY_KEYWORDS` (L21): tuple extended from 6 to 10 items (incl. Blu-ray sub-tiers), aligned with the main.py whitelist.
- `main.py` (L2955): the per-URL-config quality whitelist extended from 6 to 10 items; an invalid value falls back to "原画/Origin" (rest of the parsing logic unchanged).

**5. Web panel dropdown options (modified) — `web/index.html`**

- The `room-quality` dropdown gains four new `<option>`s — `蓝光30M`/`蓝光20M`/`蓝光8M`/`蓝光4M` (right after "蓝光/Blu-ray"), preserving the default option and the existing option order…

**6. Tests (new + modified)**

- `tests/test_quality_tiers.py` (**new file, 270 lines**): 3 classes, 29 cases — `TestGetQualityCodeSubTiers` (sub-tier Chinese-name mapping / legacy names unchanged / unknown falls back to OD), `TestGetQualityIndexSubTiers` (sub-tiers fold to BD / digit semantics unchanged), `TestHuyaSubTiers` (available tier appends ratio / unavailable nearest downgrade / exsphd-driven downgrade / low-capacity room degrades to lowest available / no lower tier falls back to Origin / unknown capacity requests directly / OD unchanged / legacy UHD-exsphd label compatibility), `TestDouyuSubTiers` (BD4 rate and read-back / BD8 server-clamped / BD30·20 fold to BD8 / OD success single call / OD restricted downgrade retry / all-rates-failed returns no URL / legacy OD-rate mapping unchanged).
- `tests/test_stream.py`: `test_quality_mapping_keys_match_level_keys`/`test_quality_mapping_keys_match_bit_keys`/`test_quality_code_to_zh_keys_match_mapping_keys` changed from "set equality" to "base set ⊆ extended set and `BD_SUB_TIERS` == extended set − base set"

**Notes on the Changes**:

- **Blu-ray sub-tiers do not pollute the generic index**: index-based selection platforms (Douyin/TikTok etc.
- **Huya `ratio` is the bitrate ceiling**: measurements confirm `ratio` is appended to the FLV/HLS URL query to pick a tier, all CDN lines share the same anti-leech params, and the stream-path is unchanged (consistent with the historical `sFlvAntiCode` parsing).
- **Douyu's built-in nearest-clamp is the primary downgrade path…
- **Downgrade semantics aligned with `QUALITY_LEVEL`**: `is_downgrade(actual, requested)` judges direction by the level number (e.


## v4.0.9.2-dev (2026-08-29) — Web Panel Manual Recording Control (Global Switch + 7 Interrupt Points + Start/Stop Buttons) + Two-Round Review Fixes + End-to-End Smoke Test & Commit-Gate Triage


### Files Involved (Classified by Module)

**1. Recording-chain global switch — `main.py`**

- New module-level `recording_enabled: bool = True` (L210)…

**2. Running-list cleanup — `src/notify.py`**

- New `remove_room_from_running(record_url)` (L153): idempotently removes the room from `running_list` on thread exit (membership check first, decrements `monitoring` only on actual removal, shares `record_state_lock` with `clear_record_info`), guaranteeing rooms can be re-spawned after "stop recording" followed by "start recording".

**3. Web API & status exposure — `src/web_api.py` + `src/recorder_status.py`**

- `web_api.py`: new `POST /api/recording/toggle` (L249-258) — request body `{"enable": bool}`, flips `main.recording_enabled` and returns `{"ok": true, "recording_enabled": ...}`
- `recorder_status.py`: status JSON gains `"recording_enabled": main.recording_enabled` (L109) — after page refresh/reconnect the frontend restores the true button state via 2s polling (orthogonal to `engine_alive`).

**4. Web panel entry — `web.py`**

- Sets `main.recording_enabled = False` **before** the engine thread starts (L188-189, set-then-`start()` eliminates the startup race): the panel defaults to not recording, while config hot-reload / scheduler / danmaku monitoring keep running, awaiting manual trigger.

**5. Frontend — `web/index.html` + `web/app.js` + `web/style.css`**

- `index.html` (L39-46) adds a "recording control" strip: state indicator (twin spans `Recording active`/`Recording stopped` toggled via `hidden`) + start/stop buttons, copy served by static `data-i18n` translation (applies immediately on language switch).
- `app.js`: new `renderRecordingControl` (mutually exclusive button enable/disable, `engine_alive` linkage, state-label toggling) and `toggleRecording` (POST toggle → success toast → status refetch in its own try/catch so a refetch failure stays silent and the 2s polling syncs, instead of a misleading "operation failed" toast)…
- `style.css` (L248-275) adds the control-strip styles: primary-colored start button / red stop button / disabled state (opacity + pointer-events disabled), consistent with the existing card style.

**6. Tests (new + modified)**

- `tests/test_web_api.py`: new `TestRecordingToggle` (2 cases — 401 without auth, toggle flip writing the real module attribute).
- `tests/test_record_failure_feedback.py` (**new file**): `test_check_subprocess_interrupts_when_recording_disabled` verifies that with `recording_enabled=False` the ffmpeg polling loop interrupts, graceful termination is called exactly once, and no success/failure samples are recorded…

**7. Documentation (new)**

- `docs/web-recording-control-changelog.md` (**new**): feature change summary — background, design (global switch + multi-entry interrupts), key design decisions (including the corrected "stop semantics = active graded graceful termination" wording), integration points, test verification, known limitations, and closure of all 5 follow-up items (commit / review / smoke / persistence evaluation / per-room switch decision).
- `docs/security-triage-2026-08-29.md` (**new**): finding-by-finding triage of the 44 Mimosa L3 commit-gate alerts — SSRF (hardcoded official download sources), path traversal (fixed-constant paths plus the existing `clean_name` sanitizer whose `main.rstr` regex includes `/ \ : .`), command injection (plain JS operations inside PyExecJS), hardcoded credentials (public platform client tokens), weak randomness (non-crypto jitter) — all pre-existing false positives or upstream patterns, Zip-Slip already guarded by `realpath` checks, none on this feature's code.
- `CODE_WIKI.md` / `CODE_WIKI_EN.md`: this changelog entry added (bilingual sync).

**Change Notes**:

- **Stop semantics is active graded graceful termination, not "natural finish"**: the 1s polling loop detects the switch being off and terminates ffmpeg — 'q' is written first so it finalizes the file tail (TS/FLV/segments uncorrupted), then escalates terminate → kill…
- **Error-sample isolation is a prerequisite of the breaker system**: stop-period interrupts do not count as `record_error` samples, preventing a user "stop recording" from being misread as mass recording failures that would trigger error back-pressure downsizing or per-platform circuit breaking.
- **`recording_enabled` is not persisted (follow-up item 4 evaluation)**: persisting `True` would auto-resume recording after a panel restart, re-introducing "auto-record on Web startup" through the back door — exactly the behavior this feature's P0 requirement 1 removes…
- **Per-room switch remains deferred (item 5)**: consistent with known-limitation #1 — "record all / stop all" is the common Web need…
- **All 7 interrupt points are early-return patterns**: normal flow paths unchanged…


## v4.0.9.2-dev (2026-08-28) — Performance Review Optimization Landed (P1~P5 + Probe-Client Reuse + Backoff-Window Self-Healing + Web Log-Sink Rebuild + Huya FLV-first)


### Files Involved (Classified by Module)

**1. Stream Probe & Source Selection (Perf P1 + Fixes one/four) — `src/stream_select.py`**

- **P1 probe-client reuse**: `select_source_url` shares one `httpx.Client` across all candidates of a single round (`finally` closes it…
- **Fix one — backoff window aligned to the main loop**: new `_PROBE_BACKOFF_INTERVAL_MARGIN = 70.0`
- **Fix four — Huya FLV-first**: new `_FLV_FIRST_PLATFORMS = ("虎牙直播",)` (**Douyu never added** — its guest-state FLV is cut off at ~70s, so it must stay HLS-first)…

**2. Recording Main Chain (Fix two) — `main.py`**

- In `check_subprocess`, the success branch (parsing the address after `-i` in `ffmpeg_command`) calls `clear_ffmpeg_reject(...)`, pairing with the `mark_ffmpeg_reject` in the failure branch — clearing that host+path's backoff so a recovered route is not skipped…

**3. Concurrency Scheduling (Perf P4) — `src/scheduler.py`**

- `import time` hoisted to module top (`_now` / `_sleep` no longer import inside functions)…

**4. Synchronous HTTP (Perf P2) — `src/sync_http.py`**

- New `_thread_local = threading.local()` and `_session()` (thread-local `requests.Session` reuse…

**5. Utils / Parsing / Config (Perf P5)**

- `src/utils.py`: `remove_emojis`'s ~400-char emoji pattern hoisted to the module-level constant `_EMOJI_PATTERN` (no per-call `re.compile`).
- `src/stream_select.py`: `contains_url`'s pattern hoisted to the module-level constant `_URL_PATTERN`.
- `src/spider.py`: new `_BANDWIDTH_PATTERN` / `_DOUYIN_HEVC_FLV_PATTERN`, replacing 4 in-function `re.compile` calls (`spider.py:178/202/1844/1918`).
- `src/web_config.py`: `update_config_line`'s "compile regex by key" changed to `functools.lru_cache(maxsize=128)` (`web_config.py:228`).

**6. Main-Loop Deduplication (Perf P3) — `main.py`**

- `url_comments` / `line_list` / `url_line_list` changed from list to `set`

**7. Logging (Fix three) — `src/logger.py` + `web.py`**

- `src/logger.py`: new module-level `_console_sink_id` captures the `logger.add` return value (lines 36/58)…
- `web.py`: `_enter_background_mode` (`web.py:103`), after redirecting `sys.stdout/stderr` to `logs/web_console.log` and `SW_HIDE`-hiding the console window, calls `rebind_console_sink()` to rebuild the console sink (loguru binds the concrete object at `add()` time and does not follow a later reassignment of `sys.stderr` — without a rebuild all DEBUG/WARNING went to the hidden window).

**8. Tests (New + Modified)**

- `tests/test_stream_select.py`: 3 client fakes gain a `headers` parameter on `head` / `stream`
- `tests/test_sync_http.py`: 4 proxy cases' patch target changed from `src.sync_http.requests` to `src.sync_http._session`.
- `tests/test_logger_console_sink.py` (**new**, 3 cases): follows the current stderr / replaces rather than appends / silent when `None` (assertions must `logger.complete()` to drain the `enqueue=True` async queue).

**9. Documentation (This Entry)**

- `CODE_WIKI.md` / `CODE_WIKI_EN.md`: changelog gained this entry (CN/EN in sync).
- `PERF_REVIEW_2026-08-28.md` (**new**): performance-review report (bottleneck list P1~P7, local-benchmark measurements, three-round real-device conclusions, three misjudgment corrections).
- `AGENTS.md`: 6 regression-prevention conventions added (probe-client reuse scope = one selection round, never disable keepalive "for safety", backoff window must be ≥ one main-loop interval, clear backoff on record success, rebuild Web-background sink, Huya FLV-first with Douyu excluded).

**Change Notes**:

- **P1 real speedup is ~5.
- **"headers not forwarded" was not a defect**: httpx `_merge_headers` *merges* rather than replaces, so client-level UA/Referer/Cookie still apply…
- **The backoff-window mismatch was the true root cause**: fixed 60s < 120s loop interval, so after a ffmpeg fast-failure records the backoff, the next round at T+124s arrives long after expiry → hits the same dead route again.
- **Concurrent-connection peak measured at 1**: candidates are validated serially, so reuse does not raise the instantaneous connection count and actually reduces new connections (old 4 → reused 1, 70.
- **Huya FLV-first payoff**: three rounds of real devices (880214 / chuhe etc.


## v4.0.9.1-dev (2026-08-28) — CI Workflow Optimization & Network-Install Retry Consolidation (retry Composite Action) + PEP 758 Formatting Landed via black 26 + i18n Extractor Fixes + Eight-File Repository Metadata Sync


### Files Involved (Classified by Module)

**1. CI / GitHub Actions (New Feature + Modifications)**

- `.github/actions/retry/action.yml` (**new**): composite action `retry` — the unified retry wrapper for network-install commands.
- `.github/workflows/ci.yml` (rewritten; job structure and gate semantics unchanged):
  - `actions/checkout` v5→v7 and `actions/setup-python` v6→v7 (WebSearch confirmed v7 is the current latest major for both, aligned with build-release.
  - 9 inline retry scripts (pip ×5 / apt ×3 / build-verify deps ×1, ~12 lines each) replaced with retry composite-action calls (apt backoff kept at the original 10s);
  - apt installs aligned with build-release.
  - header comments gained the job topology diagram (setup fanning out to six parallel jobs → ci-summary aggregation) and the responsibility boundary "this workflow stops at verification and contains no deployment"
- `.github/workflows/build-release.yml`: 4 inline retry scripts (choco / apt / brew / pip) replaced with the retry composite action (backoff values match the original scripts one-to-one: system package managers 15s, pip 10s)…

**2. Internationalization Module (Modifications — Formatting + Maintenance Tooling)**

- `i18n.py` + `scripts/compile_po.py`: after an earlier same-day entry converted 4 `except` clauses to tuple parentheses, black 26.
- `scripts/extract_i18n_strings.py` (**two defect fixes; first recorded into the directory tree and §8 maintenance workflow by this entry**):
  - `is_valuable()` reworked: the old logic stripped braces then looked for letters, but identifiers inside placeholder expressions (`color`/`Color`) are letters too, so pure-placeholder templates (`{color}{text}{Color.RESET}` / `{rec_info}/{filename}`) were falsely reported as "missing, to translate"
  - `load_catalog_keys()`: the po header empty `msgid ""` is now excluded before comparison — JSON/YAML catalogs intentionally do not contain it (runtime loading pops it too)…

**3. Repository Metadata Eight-File Sync (Modifications)**

- `requirements.txt` / `Dockerfile`: 4 comment references to the **nonexistent `src/danmaku/` path** corrected to the actual locations (`src/ws_client.py` / `src/proto/douyin_pb2.py` / `src/platforms/bilibili.py` / the collector factory chain) — the danmaku modules actually live in src/ root, platforms/, and proto/…
- `.dockerignore`: 16 exclusions added — `.mimosa/` plus 7 local tool directories (`.qoder/`, `.agents/`, `.pnpm-store/`, `.dsh-validation/`, `.ego-browser-test/`, `.plugin-src/`, `.tmp-dps-extract/`, `pytest-cache-files-*/`, kept in sync with .
- `.gitignore`: added `.mimosa/` (previously excluded in all four pyproject tool configs yet still showing as untracked `?? .mimosa/` in git status) and a defensive `pytest-cache-files-*/` entry.
- `pyproject.toml`: basedpyright exclude cleaned of 2 already-deleted dead directories (`pytest-cache-files-g1bpkgza` / `pytest-cache-files-wt8ppn27`)…
- `docker-compose.yaml`: the `.env` example version `4.0.8.3` → `4.0.9.1` (aligned with the current pyproject version).
- `AGENTS.md`: module count 39 → 41 (measured: 31 in src root + 8 in platforms + 2 in proto)…
- `.coveragerc-concurrency`: item-by-item verification against pyproject `[tool.coverage.*]` — fully consistent (source / omit / exclude_lines identical…

**4. Documentation (This Entry)**

- `CODE_WIKI.md` / `CODE_WIKI_EN.md`: directory tree gained `.github/actions/retry/`, `scripts/extract_i18n_strings.py`, `scripts/check_coverage.py`, `uv.lock` (and removed the duplicated `.coveragerc-concurrency` entry)…

**Change Notes**:

- **Clarifying the PEP 758 round-trip**: an earlier same-day entry converted the 4 `except` clauses to tuple parentheses (then judged "safest for ≥3.
- **Why consolidate retries**: the two workflows had 13 nearly identical 12-line inline retry loops…
- **macOS brew step split**: `brew trust aws/tap` is idempotent with a `|| true` fallback…
- **.
- **Basis for excluding scripts/ from the image**: grep verified that all root entry scripts and `src/**` have zero references to `scripts/`


## v4.0.9.1-dev (2026-08-27) — i18n Localization System Fix (Python 2-style `except` Multi-Except → Tuple Parentheses) + zh_CN.mo Recompile


### Files Involved (Classified by Module)

**1. Internationalization Module (Modifications)**

- `i18n.py`: three `except` multi-except comma forms converted to tuple parentheses (behavior unchanged):
  - `i18n.py:202` `except OSError, ValueError:` → `except (OSError, ValueError):`;
  - `i18n.py:218` `except OSError, ValueError, yaml.YAMLError:` → `except (OSError, ValueError, yaml.YAMLError):` (the three-except comma form is illegal in every Python version and was the true fatal point);
  - `i18n.py:320` `except ValueError, AttributeError:` → `except (ValueError, AttributeError):`.
  - After the fix `py_compile` passes and `import i18n` works (`_load_translations(locale_path, 'zh_CN')` loads 496 entries).
- `scripts/compile_po.py`: `scripts/compile_po.py:128` `except AttributeError, OSError:` → `except (AttributeError, OSError):`. After the fix the compile script runs normally.

**2. Build Artifact (Regenerated)**

- `i18n/zh_CN/LC_MESSAGES/zh_CN.mo`: after the syntax fix, `python scripts/compile_po.py` regenerates it (aligned with the current `zh_CN.po`, 496 entries including the gettext header, `--check` byte-level synced).

**Change Notes**:

- **Why it was a blocking defect**: the first-pass "full replenishment" `zh_CN.mo` was in fact never written to disk (the compile script itself could not be parsed by Python).
- **Correction to the first-pass "PEP 758 legal / no change" assessment**: the same-day second-pass review entry claimed "all 16 `except A, B:` across the repo are legal under 3.
- **§8 translation-file table entry count**: updated from 492 to 496 in tandem (aligned with the current 496 entries in `.po`/`.mo`).


## v4.0.9.1-dev (2026-08-27) — Second-Pass Review Fixes (compile_po --check Always-True Gate + Direct-Download Failure Sampling Gap + i18n/Web Gap Closure)


### Files Involved (Classified by Module)

**1. Build / CI / Community Templates (Modifications + Deletions)**

- `scripts/compile_po.py`:
  - **`write_mo()` converted to pure in-memory output** (removed the `path.write_bytes()` side effect and the `path` parameter): previously `main()` unconditionally called `write_mo(entries, MO_PATH)` before the `--check` branch, overwriting `.mo` with the freshly compiled result…
  - **Disk-write decision moved to the caller**: non-check mode explicitly does `MO_PATH.write_bytes(fresh)` before printing the success message…
  - Header usage comment updated with the "zero side effects, no disk write" semantics.
- `.github/workflows/ci.yml`: added `- 'i18n/**'` to the paths-filter `python` filter and corrected the adjacent comment — previously the static job (including compile_po --check) did not run for translation-only changes, which was the second root cause of "edit .
- `.github/workflows/build-release.yml`: removed the leftover no-op step "Debug inputs" at the end of the release job (produced meaningless output on the tag path only).
- `.github/ISSUE_TEMPLATE/bug.yml` / `bug_en.yml` / `question.yml` / `question_en.yml`: added `- Python 3.14` to the version dropdowns (the project requires ≥3.

**2. Recording Main Chain (Modifications)**

- `main.py`:
  - **Direct-download failure sample reporting** (direct-download branch of `start_record`): after the `if download_success:` success-sample branch, added `elif record_url not in url_comments and not exit_recording: record_error(record_host)` — both "non-200" (CDN rejection, the Huya-style signature) and "network error" (httpx exceptions already swallowed inside `direct_download_stream`) surface as `return False` and never reach the outer try's `record_error`
  - **Per-round danmaku-args reset restored**: added `record_danmaku_args = None` at the top of the inner monitoring loop (before the `exit_recording` check), per the AGENTS.
  - **Two log messages normalized**: the non-200 branch of `direct_download_stream` now includes the request URL…
- `src/async_http.py` (legacy cleanup): the two bare `logger.debug(e)` calls in `_close_all_clients()` and the main except of `async_req()` were normalized to `f"<action>: {url} - {type(e).__name__}: {e}"` format (matching the existing example in `get_response_status` in the same file…

**3. Web Config & API (New Features + Modifications)**

- `src/web_config.py`: added `append_config_line(config_file, section, key, value)` — line-level append for missing-key backfill (`update_config_line` only replaces lines and returns False when key or section is missing).
- `src/web_api.py`: `PUT /api/language` write-back fallback chain — when line-level replacement fails (historical config.

**4. Web Frontend (Modifications)**

- `web/app.js`: about ten hardcoded Chinese strings switched to the embedded four-language dictionary via `t()` (wrapped in `esc()` consistently with the rest of the file) — recording table empty state `empty.noRecording`, danmaku stream empty state `danmaku.noData`, truncation notice `danmaku.truncated`, toggle toast `toast.enabled/disabled`, op-failed `toast.opFailed`, config page empty state `config.none` and load failure `loadFailed`, file list empty state `files.emptyDir` plus enter/download buttons `rooms.enter/rooms.download`, download failure `toast.downloadFailed`.

**5. Tests (New Features + Modifications)**

- `tests/test_record_failure_feedback.py`: added httpx streaming fakes `_FakeStreamResponse` / `_FakeHttpClient` (`__exit__` annotated `-> None` to satisfy mypy `exit-return`), plus 2 cases: `test_direct_download_stream_rejects_non_200_as_failure` (non-200 → False failure contract) and `test_direct_download_stream_writes_chunks_on_success` (chunk-by-chunk writes → True), 5 → 7 cases…
- `tests/test_web_api.py`: added `test_put_language_missing_key_appends_and_succeeds` (PUT no longer 500s when `[录制设置]`/`language` are absent, backfill lands correctly and leaves `[Web]` untouched) and `test_append_config_line_edge_cases` (target section present with interleaved comments / target section last with no trailing newline / section missing), also correcting the old comment that admitted "update_config_line requires the key to pre-exist…
- `tests/test_i18n.py`: `test_po_and_mo_in_sync` adapted to the new `write_mo()` signature (no path parameter; compare against the returned bytes directly), removing the now-redundant `tempfile` import.

**6. Documentation (Modifications)**

- `CODE_WIKI.md` / `CODE_WIKI_EN.md` (this entry): directory-tree tests annotations updated (test_record_failure_feedback 7 cases…

**Change Notes**:

- **Why --check must be side-effect free**: a sync check fundamentally compares "working-tree artifact ↔ committed artifact"
- **Condition design of the direct-download sample branch**: `record_url not in url_comments and not exit_recording` distinguishes "real failure" from "manual interruption" — interrupted rounds lead to thread exit and must not inject noise samples into the breaker…
- **PEP 758 clarification** (important for future reviews): since Python 3.
- **append_config_line edge handling**: the new boundary tests caught and fixed one initial-version defect — when the source file's last line had no trailing newline, the "insert mid-file" path corrupted that last line via concatenation…


## v4.0.9.1-dev (2026-08-27) — Code-Review Fixes (Circuit-Breaker Probe Lease Self-Healing + Scheduler Success Sampling) + Scheduler Thread-Safety Hardening + Full i18n Catalog Replenishment (288 → 492 entries)


### Files Involved (Classified by Module)

**1. Concurrency Scheduling Module (New Features + Modifications)**

- `src/scheduler.py`:
  - **Added probe lease** (high-severity fix): module constant `_PROBE_LEASE_SECONDS = 60.0`
  - **Config-field locking** (thread-safety hardening): `_compute_capacity()` now takes a single lock to snapshot all mutable inputs (mode/config/active count/error window, multi-field read consistency)…
  - **`host_of()` comment fix**: the old comment claimed "strip port / custom direct links fall back to the path itself", which did not match the implementation (which keeps the port, returns only the host, and uniformly maps broken URLs to the shared `"unknown"` breaker key)…
- `main.py`: the parse-success branch of `start_record` (non-empty `port_info["anchor_name"]`) now reports `record_success(record_host)` — symmetric with the `record_error` in the parse-failure branch.
- `src/notify.py`:
  - The three-arg `getattr(main, "scheduler", None)` in `record_error` / `record_success` replaced with direct `main.scheduler` access (AGENTS.
  - The three bare `logger.error(e)` calls in `run_script` now include "action + object + exception type" (the `PermissionError`/`OSError`/`ValueError` branches all carry `command` and `type(e).__name__`).

**2. Internationalization Module (Modifications)**

- `i18n.py`: the `except` of `_load_yaml_catalog()` now also catches `yaml.YAMLError` (ParserError/ScannerError are not OSError/ValueError subclasses…
- `i18n/zh_CN/LC_MESSAGES/zh_CN.po`: 204 new entries (288 → 492), with a dated section comment and the header `PO-Revision-Date` updated to 2026-08-27…
- `i18n/en_US.json` / `i18n/en_GB.json` / `i18n/zh_TW.yaml`: appended the same 204 entries (each 288 → 492), four-language key sets fully identical.

**3. GUI Module (Modifications)**

- `gui.py`: new `_bootstrap_crash_reported` module-level flag — after `_bootstrap_error_sink` handles a top-level `main()` exception and sets the flag, the excepthook installed by `_install_crash_sink` skips the re-raised exception (previously the same exception produced two identical error dialogs and a doubly-stacked log file: `"w"` overwrite + `"a"` append).

**4. Tests (New Features)**

- `tests/test_scheduler.py`: added `test_platform_breaker_probe_lease_regrants_after_timeout` (the full self-healing chain: lease expiry → re-grant → new probe reports success → closed), 15 → 16 cases.
- `tests/test_i18n.py`: added `test_load_yaml_catalog_corrupted_returns_none` (a corrupted YAML returns None for graceful degradation instead of raising).

**5. Documentation (Modifications)**

- `AGENTS.md`: version 4.
- `CODE_WIKI.md` / `CODE_WIKI_EN.md` (this entry): Section 8 translation-file table entry counts 282 → 492, coverage updated…

**Change Notes**:

- **Probe lease vs.
- **Zero behavioral impact of locking**: the order of snapshot/write inside the lock and `recompute()` after lock release guarantees no nested lock holding (`Lock` is non-reentrant)…
- **i18n replenishment methodology**: the authoritative baseline is static AST extraction (all constant args of `print()` + the first constant arg of `logger.debug/info/warning/error/...` with f-string template reconstruction), excluding 5 items of no translation value (pure format templates like `{color}{text}{Color.RESET}`, `{'=' * 60}` separator lines, `{rec_info}/{filename}` with no natural language, and 1 near-duplicate of an existing key differing only in placeholder spelling)…


## v4.0.9-dev (2026-08-24) — High-Concurrency Multi-Platform Recording Scheduling & Resource Management Optimization (Adaptive Concurrency + Per-Platform Circuit Breaking)


### Files Involved

- New `src/scheduler.py`: the scheduling core module, containing `ResizableSemaphore` / `PlatformBreaker` / `ConcurrencyScheduler` / `host_of`.
- Modified `src/notify.py`: `record_error` / `record_success` gained a `key` parameter and delegate to `scheduler` to record the per-key error budget…
- Modified `main.py`: imports `ConcurrencyScheduler` / `ResizableSemaphore` / `host_of`
- New `tests/test_scheduler.py`: 12 unit tests covering semaphore resizing, breaker state machine, adaptive capacity scaling/floor, per-key isolation, and the recording-concurrency soft cap.
- Fixed 21 Python 2-style `except A, B:` syntax errors in 14 source files (`build_exe.py`, `gui.py`, `i18n.py`, `scripts/check_coverage.py`, `scripts/compile_po.py`, `src/collector.py`, `src/config_io.py`, `src/recorder_status.py`, `src/spider.py` (2), `src/ttwid.py`, `src/web_config.py`, `src/ws_client.py`, `src/platforms/bilibili.py`, `src/platforms/douyu.py`), making the project importable/testable under Python 3 (a pre-freeze historical leftover that did not affect the frozen exe).

**Change Details**:
- **`ResizableSemaphore`**: a context-manager semaphore supporting runtime `set_value` capacity changes — increasing wakes waiters, decreasing only lowers the ceiling without forcibly reclaiming held permits, eliminating the race of the old "destroy-and-rebuild semaphore" approach.
- **`PlatformBreaker`**: a per-key circuit breaker with a closed→open→half-open state machine.
- **`ConcurrencyScheduler`**: the hub.
- **`host_of(url)`**: extracts the URL host (lowercased, stripped of port/path/query) as the breaker key; custom flv/m3u8 direct links fall back to the path itself.
- **`notify.py` wiring**: `record_error(key=None)` / `record_success(key=None)`, in addition to updating `main.error_window` / `error_count`, delegate via `getattr(main, "scheduler", None)` to record the per-key breaker budget…
- **`main.py` wiring**:
  - The global was changed from `semaphore: threading.Semaphore = threading.Semaphore(1)` to `scheduler: ConcurrencyScheduler | None` (None placeholder), `semaphore: ResizableSemaphore`, and `recording_semaphore: ResizableSemaphore`.
  - `main()` initializes `scheduler = ConcurrencyScheduler(configured_limit=max_request)` on first run and points `semaphore` / `recording_semaphore` at its attributes…
  - `start_record`: `record_host = host_of(record_url)` (with `record_host = ""` pre-set at the top of `while True`, before `try`, to eliminate possibly-unbound)…
  - `check_subprocess`: wraps the `while process.poll() is None:` recording loop in `recording_semaphore` `acquire()` / `release()` (try/finally), enabling an optional cap on simultaneous ffmpeg recordings.
- **Test additions**: `tests/test_scheduler.py` with 12 cases (including corrections to two test premises: ① `ResizableSemaphore(0)` is a valid paused state…


## v4.0.9-dev (2026-08-24) — Four-Language Catalog Unification & British/American Split + Build-Script Strings Added + zh_CN.mo Recompiled


### Files involved

- Modified `i18n/zh_CN/LC_MESSAGES/zh_CN.po`: appended 6 build/smoke constant strings, bumped PO-Revision-Date to 2026-08-24, refreshed header comments.
- Modified `i18n/en_US.json`: added 6 new strings; unified the whole file to American spelling (removed British leftovers such as minimise/minimised/cancelled).
- Modified `i18n/en_GB.json`: added 6 new strings; rewritten to genuinely British spelling (minimise/minimises/minimised/cancelled), differing from en_US only in the 4 spelling-sensitive entries.
- Modified `i18n/zh_TW.yaml`: added 6 new strings (Simplified→Traditional conversion, e.g. 跳过→跳過, 开始下载运行时二进制→開始下載執行時二進位檔).
- Regenerated `i18n/zh_CN/LC_MESSAGES/zh_CN.mo` (28,697 bytes) and verified it syncs with the .po.

**Change details**:
- **Four-language key-set consistency**: used the source constant strings as the authoritative baseline, covering the full runtime scope…
- **Build-script strings added**: build_exe.
- **American/British split**: en_US was internally inconsistent (mixed British minimise, cancelled, etc.


## v4.0.9-dev (2026-08-23) — Recording-Result Feedback to Scheduler + Probe Backoff Marking (Root Fix for Huya 403 Dead Loop)


### Files touched

- `main.py`: `check_subprocess` adds `_proc_started_at = time.time()`
- `src/stream_select.py`: new public entry `mark_ffmpeg_reject(url, platform)` (delegates to `_mark_probe_reject`)…
- `src/recorder_status.py`: new `_live_network_capacity()` returns scheduler live value (`scheduler.network_semaphore.value`), falls back to `main.max_request` when scheduler is not ready…
- New `tests/test_record_failure_feedback.py`: 5 unit tests covering success / fast-fail+backoff / slow-fail-no-mark / missing `-i` flag / capacity fallback.
- `tests/test_stream_select.py`: adds `test_mark_ffmpeg_reject_marks_backoff` (cross-round token hit + non-whitelisted platform no-op).
- `AGENTS.md`: new "Recording-result feedback conventions" subsection.

**Details**:
- **Failure sample reporting**: `check_subprocess` in its `return_code` branch — success (rc==0, stream ends normally/streamer goes offline) records one success sample per room host to keep `error_window` error-rate accurate…
- **Fast-fail probe backoff**: `time.time() - _proc_started_at <= _FFMPEG_FAST_FAIL_SECONDS` (20 s) signals a fast failure (signature of input-open CDN rejection…
- **Slow-fail exemption**: `-reconnect_delay_max 60` exhaustion (>60 s) is stream interruption / reconnection-exhaustion, not "line unreachable" — only records failure sample, does not mark probe backoff (line was previously reachable…
- **Malformed-input fallback**: if `ffmpeg_command` lacks `-i`, `except ValueError` catches, records failure sample only, skips backoff mark.
- **Capacity display**: `_live_network_capacity()` reads `scheduler.network_semaphore.value` (when scheduler is ready), else falls back to `main.max_request` (early init / test env)…
- **Direct-download alignment**: `direct_download_stream` success path adds `record_success(record_host)` to align with ffmpeg-path semantics (failure already has `record_error` in the except branch).


## v4.0.9-dev (2026-08-23) — Dual Network-Concurrency Modes (Adaptive vs Fixed)


### Files touched

- `src/scheduler.py`: `ConcurrencyScheduler` gains a `_dynamic_mode` field plus `set_dynamic_mode(enabled: bool)` and `dynamic_mode` property.
- `main.py`: the hot-reload loop now appends `scheduler.set_dynamic_mode(new_recording_limit == 0)` right after `scheduler.set_recording_limit(...)`, wiring in the "0=dynamic, non-zero=fixed" switch…
- New 3 cases in `tests/test_scheduler.py`: `test_scheduler_fixed_mode_pins_capacity_to_configured_limit` (fixed capacity stays pinned regardless of task count…
- `AGENTS.md`: concurrency-model section updated with the mode semantics (`set_dynamic_mode` integration, dual-branch logic, orthogonality of per-key breaker and mode, 15 scheduler cases).

**Change details**:
- **Mode semantics**: `最大同时录制数(0为不限制)` = 0 enables adaptive scaling (network capacity scales with active task count, floor 8 / ceiling 128, gently reduced under extreme error rates but never below the safety floor).
- **Recording-concurrency cap unchanged**: still governed by `scheduler.set_recording_limit(...)`, unaffected by mode switching.
- **`adjust_loop` becomes a recompute no-op in fixed mode** (`recompute()` skips `set_value` when the target capacity is unchanged), so the same daemon loop is safe to reuse.
- **Logging**: `set_dynamic_mode()` emits `并发模式: 动态调速（网络容量随活跃任务数自适应，当前 <n>，下限 <min>，上限 <max>）` or `并发模式: 固定（忽略动态调速器，网络容量固定为 <n>，来源: 配置「同一时间访问网络的线程数」）` on first broadcast / mode change…

## v4.3.0-dev (2026-09-27) — Today's changes classified by module: four release-chain fixes + findings 4/5/6 + the four-doc size pass + the AGENTS.md trim + metadata and consistency sync

### Today's change inventory by module (added / modified / removed + file paths)

> Reached by the pointer in the wiki entry of the same title; the wiki keeps only the per-module summary. Line endings: `build_exe.py`, `AGENTS.md`, both wikis and both appendices stay pure CRLF, `tests/test_build_exe.py` stays pure LF (identical before and after).

#### 1. Packaging and release chain (`build_exe.py`)

- **Modified**: `make_zip()` builds the artifact name as one f-string (no `Path.with_suffix(".zip")`); added the structural guard that `zip_path.parent` must still be `DIST_DIR`; the `--dual` branch now keeps both return values and prints the real artifact names; the two Linux slots of `_FFMPEG_DOWNLOAD_URLS` moved from the rolling `releases/latest` to the month-end tag `autobuild-2026-08-31-13-27`, with `_PINNED_RUNTIME_SHA256` linux-x64 / linux-arm64 set to `182c1b50…` / `e2dd447c…`; the eight slots wrongly turned into `OFFICIAL_SIGNATURE_PIN` were re-pinned from the official channels.
- **New functions**: `_clean_stale_release_zips()` and `_drop_stale_release_zips()` (prune stale `{APP_NAME}-v*.zip` leftovers in `dist/` before packaging and print the removed list), `_assert_dual_zips_are_two_files()` (the two return paths must differ and both must exist on disk, else `SystemExit`).
- **New argument validation**: `--dual` and `--no-zip` are mutually exclusive and fail fast (the `--dual` branch never reads `no_zip`).
- **Removed**: nothing. No function, download source or platform branch was deleted; `--dual` still emits both lite and full zips.

#### 2. CI and release workflow (`.github/workflows/build-release.yml`)

- **New job**: `release-guard` (`needs: [prepare, build]` plus `if: always() && release path && needs.build.result != 'success'`) deletes the empty/partial Release pre-created by `release-create` via `gh release delete` (tags are kept by default) and leaves a `::warning::`.
- **New step**: `Verify dist contains both lite & full zips` (`shopt -s nullglob` counting, `exit 1` when either variant is missing); `fail_on_unmatched_files: true` deliberately not relaxed.
- **Parallel-edit log**: this file was edited at 08:14 today outside this session to add `| tee build_exe.log` and an artifact listing step (27,171 -> 27,812 B); this session never touched it. Verified that under `pipefail` a `tee` does not swallow `SystemExit`.

#### 3. Tests (`tests/test_build_exe.py`, single file 100 -> 105 passed)

- **New cases (9 functions / 10 assertion units)**: `test_make_zip_name_keeps_dotted_version_and_variant_suffix` (parametrized `-lite` / `-full`), `test_dual_suffixes_do_not_collide_on_one_zip`, `test_make_zip_refuses_name_containing_path_separator` (both parameter positions, using `'/'` rather than `os.sep`), `test_dual_and_no_zip_are_mutually_exclusive` (asserts `order == []`), `test_dual_build_prunes_stale_zips_before_first_zip`, `test_no_zip_build_keeps_existing_dist_zips`, `test_dual_build_aborts_when_both_variants_land_on_one_zip`, `test_dual_build_aborts_when_a_variant_zip_is_missing`, `test_clean_stale_release_zips_only_touches_own_artifacts`.
- **Stub rework**: the `make_zip` stub in `_stub_build_steps()` no longer returns the constant `Path("stub.zip")`; it derives the name from `suffix`, really writes bytes, and repoints `build_exe.DIST_DIR` at `tmp_path` (otherwise the tests would delete the user's real `dist/` artifacts).
- **Comment corrections**: artifact-name example `windows-x64` -> `windows-amd64`; "the two cases above only assert the file exists" rewritten into the precise per-test judgement.

#### 4. Root conventions and documentation

- `AGENTS.md` (modified): the `make_zip` item gained judgements (4) and (5) plus all nine regression-lock names; the F-14 protobuf item's declared range was corrected from `>=6.31.1,<8` to `>=6.33.5,<8` (the floor had been raised on 2026-09-26, so the old wording was a falsified statement); volume trimmed -1.4% (readings turned into pointers, three genuine duplications merged, the two same-cause `PYTHONUTF8` / `errors="replace"` items merged), 97,034 -> 95,715 B.
- `CODE_WIKI.md` / `CODE_WIKI_EN.md` (new entries): the `^### v` count rose from 169 (09:22 today) to **173 = 173** - one per release-chain fault, one for findings 4/5/6 plus the doc size pass, one for the `AGENTS.md` trim, and this overview.
- `CODE_WIKI*.md` (structural pass): 73 historical "Files involved (classified by module)" inventories relocated into this appendix (41 zh / 32 EN, 213,734 B) leaving the section heading plus one pointer line; 109 (zh) / 181 (EN) `…`-truncated table cells restored by unique prefix match against `.workbuddy/docold` (+18,439 / +33,117 B); "Document Statistics and Index" switched to a command-plus-timestamp discipline and gained the "Reference Sub-Document Index"; nine Chinese comment lines inside two EN bash blocks translated; step 4 of "Packaging and Release" corrected (smoke runs after both zips, per MID-2254) and the stale `ChallengePageError` (removed 2026-09-23 under MIN-2267) replaced with the real exception classes.
- `README.md` / `README_EN.md`: byte-identical (104,040 / 123,017 B) during the consistency audit, then updated the same day by the version-entry sync, which folded the 09-26 ~ 09-27 changes in; now 109,648 / 129,644 B with all five subsections matching one-to-one in count (🐛 9 / ✨ 12 / ⚠️ 9 / 🛠️ 7 / 🧪 4). Measured: 0 trailing-whitespace lines, 0 multi-blank runs, only 1 line duplicated verbatim from the wiki, and no historical inventories worth relocating; the changelog is deliberately not compressed.

#### 5. New reference sub-documents and local records

- `docs/agent-reference/changelog-file-inventories.md` (new, 130,064 B) and `docs/agent-reference/changelog-file-inventories-en.md` (new, 98,458 B): hold the 73 relocated inventories plus this block, pure CRLF.
- `docs/agent-reference/session-learnings.md` (six 2026-09-27 learnings appended: assert artifact names themselves, mutually exclusive flags must not be half-honored, verify sub-agent claims, relocation locator integrity, the stale-coverage-data gate, and the root-convention floor).
- `.workbuddy/memory/2026-09-27.md` (three session-log sections appended; a local cache directory already excluded by `.gitignore` and every tool exclude list).

#### 6. Build-artifact metadata (`DouyinLiveRecorder.egg-info/`)

- **Rebuilt** (ignored by both `.gitignore` and `.dockerignore`; a local artifact) using the command documented in `AGENTS.md`: `python -c "import sys; sys.argv=['setup.py','egg_info','--egg-base','.']; from setuptools import setup; setup()"`.
- **Two real drifts fixed**: `PKG-INFO`'s `Requires-Dist: h2` went from `>=4.3.0` to `>=4.4.1` (the 2026-09-26 floor raise had never propagated into the metadata), and the README embedded in `PKG-INFO` gained the v4.3.0 changelog section it was missing.
- **Fields that had not drifted**: `requires.txt`, `entry_points.txt`, `top_level.txt` and `dependency_links.txt` are byte-identical to before the rebuild (same three console scripts); `Version: 4.3.0` matches the measured `importlib.metadata.version('DouyinLiveRecorder')`.

#### 7. Verified as needing no update (with the judgement used)

- `requirements.txt` (**the only line modified**; inline comment completed, specifier untouched): the comment was cut at "...additional_headers/proxy parameters are a 14.0+ API," - a trailing comment cannot continue onto the next requirement line, so this was a genuine truncation (the other nine comma-terminated comments in the file are full-line comments that do continue). Completed from the matching `pyproject.toml` websockets comment as "on 12/13.x `connect()` raises TypeError immediately and the reconnect loop swallows it, so danmaku never connects". Re-verified after the edit: still 23 runtime entries, package-name sets still equal to `pyproject.toml`, file stays pure LF (108 lines), `tests/test_regression_2026_09_22_gates.py` 25 passed.
- `pyproject.toml [project.dependencies]`: unchanged, 23 entries equal to `requirements.txt`; the `[dev]` / `[build]` / `[gui]` extras groups match as well.
- `Dockerfile`: no hardcoded version; `ARG APP_VERSION` is declared before the `LABEL` that consumes it (asserted by `check_version.py`); the Node source is `setup_24.x` with a SHA256 pin.
- `docker-compose.yaml`: `APP_VERSION: "${APP_VERSION}"` injected from `.env`, and `pull_policy: build` prevents pulling a remote `:latest`; no `.env` exists in the workspace, which the file header already documents as "LABEL version stays empty when unset" - expected, not a defect.
- Cross-workflow constants: `python_build = 3.14` and `node_version = 24` are identical in `ci.yml` and `build-release.yml`; `black==26.5.1` / `isort==9.0.1` / `mypy==2.3.1` / `pytest==9.1.1` match what `.venv` actually has installed.
- Exclude-list homology: the 14 local tool directories and 6 runtime artifact directories appear in `.gitignore`, `.dockerignore`, `pyproject [tool.coverage.run].omit`, `.coveragerc-concurrency`, `[tool.basedpyright].exclude`, `[tool.black].exclude` and `[tool.isort].extend_skip` with no gaps.
- `config/config.ini` and `config/URL_config.ini`: **not modified**. Six sections, 143 keys; today's work added no configuration surface (`build_exe.py` contains 0 `read_config_value` / `read_config_bool` calls). Both files hold credentials, are gitignored and excluded from the image, and were not written, copied or transmitted; this record contains no real values.
- The four catalogs (`zh_CN.po` / `zh_CN.mo` / `en_US.json` / `en_GB.json` / `zh_TW.yaml`): **not modified**. 780 / 780 / 780 / 780 key sets equal (`tests/test_i18n.py::TestMultiFormatCatalogs::test_catalogs_share_same_keyset` passes); `compile_po.py --check` reports "in sync with .po (781 entries)"; `extract_i18n_strings.py` reports 0 missing. Every string added today is a `build_exe.py` `[build][FATAL]` console message - that file never calls `i18n.tr` (it runs at packaging time, before any locale resolution), so those messages are deliberately not cataloged, and none of the extractor's three blind spots (`print_colored`, `messagebox.*`, push bodies) occur in the touched files (measured 0).
