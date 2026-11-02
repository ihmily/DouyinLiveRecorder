# PHP internals: why these bugs bypass your application

## The two bugs in one paragraph each

**CVE-2026-109618, OOM corruption.** When an allocation fails, PHP (before the fix) called
`longjmp()` to abandon the request. If that happened while request memory was only partially set
up, the normal bookkeeping was skipped and request shutdown later read or branched on invalid
data. An attacker drives memory use to `memory_limit` with a request that stays inside every
visible limit: a multipart body with no usable Content-Length, parts with thousands of headers
(cheap on the wire, expensive in memory), or nested empty file fields that create `$_FILES`
metadata without counting toward `max_file_uploads`. The fix replaces `longjmp()` with a deferred
"soft" OOM at the next safe point and a hard `_exit()` at a higher threshold.

**CVE-2026-109619, stale global state.** Workers are persistent. Some global state (error,
session, object, extension) points into the request heap. When a request is cut short by a fatal
error, OOM or `max_execution_time`, the reset for that state can be skipped while the heap is
freed. The *next* request on the same worker can then touch that state before request init
resets it: use-after-free with attacker-shaped heap. Confirmed consumers are INI diagnostics
raised before request init (mod_php applies `.htaccess` and `php_value` before startup) and the
session upload-progress handler. On 8.5 the `fatal_error_backtraces` buffer is the confirmed
producer. The fix is a complete per-request state reset.

Neither bug is in your application. One needs attacker-controlled memory pressure during request
startup; the other needs a crashed earlier request plus a later request on the same worker. Both
run before `index.php` is compiled.

## Request startup order (FPM, mod_php, CGI are the same here)
1. SAPI accepts the request, `php_request_startup()`. mod_php has already applied per-directory
   INI (`.htaccess`, `php_value`) before this point; FPM applies pool `php_admin_*` here.
2. `php_hash_environment()` -> `zend_activate_auto_globals()` populates `$_POST` and `$_FILES`
   **before the script compiles**. `$_POST`/`$_FILES` are not JIT auto-globals (only
   `$_SERVER`, `$_ENV`, `$_REQUEST` are), so this always happens.
3. If `enable_post_data_reading=1` (default) and `Content-Type: multipart/form-data`,
   `sapi_handle_post()` dispatches to `rfc1867_post_handler()` in `main/rfc1867.c`. This is
   where the OOM trigger lives: per-part headers and `$_FILES` entries are allocated here.
4. `rfc1867_post_handler` emits events (`START`, `FORMDATA`, `FILE_START`, `FILE_DATA`,
   `FILE_END`, `END`) to `php_rfc1867_callback`, which `ext/session` installs at MINIT.
5. The session callback (`ext/session/session.c`):
   - `START`: returns immediately when `session.upload_progress.enabled` is off.
   - `FORMDATA`: if the field name equals `session.upload_progress.name`
     (default `PHP_SESSION_UPLOAD_PROGRESS`), stores the client-supplied value as the key and
     finds the session id (cookie, or GET/POST if `use_only_cookies=0`).
   - `FILE_START`: if a key and sid exist, `php_session_initialize()` starts the session and
     opens the save handler, then writes `$_SESSION["upload_progress_<key>"]`. This runs
     **before ordinary session init**, which is why it can consume stale session/decoder state
     left by an interrupted earlier request.
6. Only now is your script (`index.php`, WordPress, Laravel...) compiled and run.

So any URL that maps to PHP, even one that never calls `session_start()` or reads `$_FILES`,
executes steps 3-5 with attacker-controlled data. Application-layer WAF rules see a multipart
POST with one extra field.

## What each knob really does

| ini | Scope | Effect | Does NOT do |
|---|---|---|---|
| `session.upload_progress.enabled=0` | PHP_INI_PERDIR. Must be set where it applies **before request parsing**: php.ini, conf.d, FPM pool `php_admin_flag`, Apache server config. PHP says **not** `ini_set()` and **not** FPM `.user.ini`. Restart every worker. | Session callback bails at `START`. Closes the confirmed session consumer for CVE-2026-109619 and the session path seen abused in the wild. Uploads still work. PHP suggests keeping it off after patching if unused. | Stop the multipart parser running, so no effect on the OOM trigger. Does not cover other stale-state consumers. |
| `memory_limit=-1` | Set via `php_admin_value` in the FPM pool or Apache config so nothing can restore a finite limit. Restart every worker. | Removes the predictable per-request OOM the CVE-2026-109618 exploit relies on. Pair with a container/cgroup memory limit for availability. | Stop a real `mmap()` failure reaching the same path. **Never** use `RLIMIT_AS`/`RLIMIT_DATA` instead; they cause the vulnerable failure. |
| `post_max_size` low (8M without uploads, 32M with; `upload_max_filesize` below it) | PHP_INI_PERDIR | Shrinks what a request can make PHP allocate. Enforce decoded body size, part count, headers per part and nesting at the proxy too; cover requests without Content-Length. | Help on its own: in-memory size can be far larger than the wire size. |
| `fatal_error_backtraces=0` | PHP 8.5 only, PHP_INI_ALL but set administratively. Restart every worker. | Removes the strongest confirmed CVE-2026-109619 producer, the one used in the mod_php exploit. | Anything on 8.2-8.4 (directive does not exist). Other stale-state paths remain. |
| `max_input_nesting_level`, `max_input_vars`, `max_file_uploads` | various | Bound the parser's work. | Bound per-part headers (no directive for that); prevent either bug. |
| `enable_post_data_reading=0` | PHP_INI_PERDIR | PHP never reads the body: no `$_POST`, no `$_FILES`, no multipart parsing, no session callback. Strongest PHP-level stopgap for a path. | Keep `$_POST` working. Apps must read `php://input`. Only usable on JSON/API paths or during a maintenance window. Application-level OOM and fatals still possible. |
| `pm.max_requests=1` (FPM pool) | pool config | Each worker handles one request then exits, so no "later request on the same worker" for CVE-2026-109619. | Help mod_php; costs a fork per request. |
| `session.use_strict_mode=1` | PHP_INI_ALL | Rejects attacker-chosen session ids. Good hygiene; removes a classic upload-progress-to-LFI chain. | Address either CVE directly. Not in PHP's workaround list. |
| `session.upload_progress.name=<random>` | PHP_INI_PERDIR | Attacker must guess the field name. | Anything once guessed. Prefer `enabled=0`. |
| `display_errors`, `error_reporting`, `@` | any | Hide diagnostics. | **Nothing for CVE-2026-109619**: a suppressed diagnostic still touches the stale state. Remove invalid or deprecated INI settings instead. |

## Edge mitigation logic
Multipart bodies are the main trigger for the OOM path and the only route into the session
upload-progress consumer. Rejecting `multipart/form-data` at the proxy or WAF for every path
except known upload endpoints removes both with zero PHP changes, at the cost of uploads and
multipart forms elsewhere. `application/x-www-form-urlencoded` and JSON are unaffected, so logins
and normal forms keep working. `Content-Type` matching must be case-insensitive and tolerate
parameters (`; boundary=`); PHP checks only the prefix. This does not cover application-specific
OOM or fatal errors reachable with other request types.

Direct-to-origin traffic bypasses any CDN rule: close the origin to the CDN's IP ranges.

## Why CLI values are misleading
`php -i` / `php -r` load `php.ini-cli` or `/etc/php/X/cli/`. FPM and mod_php load their own
ini set plus pool overrides (`php_admin_flag` cannot be overridden by `.user.ini`). Read the
serving SAPI (probe script) before declaring a host mitigated.
