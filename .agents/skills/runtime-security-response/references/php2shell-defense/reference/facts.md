# Facts (official, PHP security advisory 2026-10-21)

Updated 2026-10-21 13:45 UTC from php.net and the php-src advisories. Earlier pre-release
reporting (a use-after-free in the multipart parser) was wrong; this file replaces it. Still run
SKILL.md step 1: follow-up releases may land.

## Confirmed by the PHP project
- **Fixed versions: 8.5.12, 8.4.27, 8.3.36, 8.2.35**, released 2026-10-21 (ahead of the 14:00 UTC
  schedule). All earlier versions of those branches are affected. PHP 8.2 reaches EOL 2026-12-31.
- **CVE-2026-109618, "RCE via OOM corruption"** ([GHSA-w8hw-w9fx-j79w](https://github.com/php/php-src/security/advisories/GHSA-w8hw-w9fx-j79w)).
  PHP used `longjmp()` to abort a request on out-of-memory. If the allocation fails while request
  memory is only partially initialised, request shutdown reads invalid state. Attackers reach OOM
  with crafted multipart bodies: no usable Content-Length, unlimited headers per part (small on
  the wire, large in memory), nested empty file fields that create metadata without counting
  toward `max_file_uploads`. Confirmed RCE on **mod_php** with default limits. PHP-FPM is
  susceptible by source analysis, no full exploit shown (FPM exits the child on startup failure).
  FrankenPHP and LSAPI likely susceptible.
- **CVE-2026-109619, "RCE via stale global state"** ([GHSA-6wmf-4rv5-p3rp](https://github.com/php/php-src/security/advisories/GHSA-6wmf-4rv5-p3rp)).
  Per-request state (error, session, object, extension) can outlive its memory when a request is
  interrupted by a fatal error, OOM or execution timeout. The **next request on the same worker**
  can use it before normal init resets it. Confirmed consumers: INI diagnostics raised before
  request init (mod_php `.htaccess` / `php_value` settings; FPM only conditionally), and
  **session upload progress**, which runs before `session_start()` and is on by default. On
  **PHP 8.5**, `fatal_error_backtraces` is the strongest confirmed producer and the basis of the
  mod_php exploit. The session path was validated against mod_php and FPM.
- Both CVSS v4.0 **9.2**, vector `AV:N/AC:H/AT:P/PR:N/UI:N/VC:H/VI:H/VA:H`. Impact: unauthenticated
  RCE as the web worker user. Reliability depends on build, extensions, allocator layout.
- **"There are no complete mitigations, updating is the only safe choice."** The official
  workarounds reduce exposure to specific paths only (see `reference/mitigations.md`).
- Linux distributions and LTS vendors received the patches in advance.
- **PHP 7.4, 8.0, 8.1**: no release, but the security team published minimal source backport
  branches: `PHP-7.4-CVE-2026-109618-109619`, `PHP-8.0-...`, `PHP-8.1-...` on github.com/php/php-src.
- **Remi's repository** will not have updates today; PHP advises switching to distro packages or source.

## Confirmed by others
- watchTowr reproduced CVE-2026-109618; Sansec and Hadrian reported in-the-wild exploitation at
  scale from the morning of 2026-10-21, mostly via the session upload-progress path. Cloudflare
  shipped "Generic Rules - Anomalous Execution" to Managed and Free WAF rulesets. NCSC UK issued an alert.
- Calif Research (finders, with OpenAI and Wiz) published the write-up on 2026-10-21
  (https://calif.io/php2shell/): found 2026-08-01, reported to PHP 2026-08-11 (second bug
  2026-08-21), RCE PoC confirmed by PHP 2026-08-15. Earliest affected path they found is PHP
  **5.4.0**. "Always exploitable under default configurations." On PHP-FPM the attacker needs an
  application path that decodes data after startup succeeds (`session_start()`, `unserialize()`,
  WordPress `maybe_unserialize()`), which every framework and CMS has. Confirmed pre-auth RCE
  against current WordPress, Drupal, Joomla, MediaWiki, Roundcube, Magento, phpMyAdmin,
  Nextcloud, **Laravel 13.11, Symfony 8.1** and WHMCS. **`post_max_size` can be bypassed in
  some configurations**; memory pressure can come from multipart bodies that stay under it. They
  call the ini mitigations "partial" and say they "do not replace a patch".
- Laravel Forge (https://laravel.com/forge/docs/knowledge-base/php-security-release-october-2026):
  Forge's automatic security updates do **not** patch PHP (PHP comes from the Sury PPA mirror,
  unattended-upgrades only takes Ubuntu's security repo). Patch every installed PHP version,
  including ones no site uses, then restart queue workers, Horizon, Octane and Reverb, which
  keep running the old binary.
- php.net's release JSON for 8.4 lagged the announcement by some minutes (still showed 8.4.26 at
  13:40 UTC). If `php-check-release.sh` says "fix not yet published" for one branch only, check
  the news page before believing it.

## No longer believed (pre-release leak)
- "Use-after-free in `php_session_rfc1867_callback`" and "bug in the multipart parser itself".
  The real bugs are OOM handling and stale global state. Multipart bodies are the main *trigger*
  for the OOM path and the session path, not the location of the bug.
- "Every version since 5.4.0" as a PHP statement: PHP lists the supported branches only. Calif's
  write-up does put the earliest affected path at 5.4.0, and the backport branches show 7.4-8.1
  are affected. Treat anything older as affected and unfixable: migrate or isolate.

## Lower exposure (reasoning, not vendor statements)
- CLI-only PHP (cron, one-shot scripts): no HTTP request lifecycle, no persistent worker reuse. Still patch.
- **Not lower exposure:** worker-mode runtimes that keep one PHP process alive across many HTTP
  requests (Laravel Octane on Swoole / FrankenPHP / RoadRunner, Reverb, ReactPHP, long-lived
  `queue:work` consuming untrusted payloads). No vendor statement either way; the "state outlives
  the request" class is exactly what they do by design. Treat them as web SAPIs: patch, then
  restart them, because a package upgrade does not restart processes started from the CLI
  (`reference/patching.md`, "Long-running PHP processes").
- `enable_post_data_reading=0` paths never parse the body, which removes the multipart OOM trigger
  and the upload-progress consumer on those paths. Application-level OOM and fatal errors remain.
- `pm.max_requests=1` in FPM removes the "same worker, later request" condition for CVE-2026-109619
  at a performance cost.

## Sources
- https://www.php.net/archive/2026.php#2026-10-21-5 (security advisory)
- https://www.php.net/archive/2026.php#2026-10-20-1 (advance notice)
- https://github.com/php/php-src/security/advisories/GHSA-w8hw-w9fx-j79w
- https://github.com/php/php-src/security/advisories/GHSA-6wmf-4rv5-p3rp
- https://watchtowr.com/intelligence/php-cve-2026-109618-faq/
- https://sansec.io/research/php2shell
- https://hadrian.io/vulnerability-alerts/php2shell-leaked-critical-php-rce-cve-2026-109618-cve-2026-109619
- https://www.ncsc.gov.uk/news/critical-security-issue-affecting-php
- https://calif.io/php2shell/ (finders' write-up)
- https://laravel.com/forge/docs/knowledge-base/php-security-release-october-2026
- https://blog.cloudflare.com/php-vulnerabilities-waf-protection/
