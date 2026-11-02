---
name: php2shell-defense
description: >-
  Prepare for, mitigate, patch, verify and hunt the critical PHP runtime RCEs CVE-2026-109618 / CVE-2026-109619 ("PHP2Shell", CVSS 9.2, fix released 2026-10-21). Use when the user mentions PHP2Shell, these CVEs, the October 2026 PHP emergency release, session.upload_progress, or asks whether their PHP hosts/containers are exposed, how to mitigate without patching, how to verify a patch, or how to hunt for exploitation. Defensive only: inventory, hardening, verification, detection. Never fetches or runs exploit code.
---

# PHP2Shell response (CVE-2026-109618 / CVE-2026-109619)

Two critical RCE bugs in the PHP runtime itself, fixed in 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12
(released 2026-10-21). CVE-2026-109618: out-of-memory handling during request startup leaves
memory half-initialised and shutdown trusts it; attackers reach OOM with crafted multipart
bodies. CVE-2026-109619: per-request global state outlives its memory after a fatal error, OOM
or timeout, and the next request on the same worker uses it; session upload progress is the
confirmed path. Both run before any application script. Frameworks, CMS plugins and
application-level checks cannot protect you. PHP: "there are no complete mitigations, updating
is the only safe choice". Everything except the patch is a stopgap.

Files in this skill:
- `scripts/php-inventory.sh`     read-only: find every PHP binary/SAPI/container on a host, versions, exposure-relevant ini values
- `scripts/php-check-release.sh` compare a version (or local PHP) against php.net live release data and the known fixed versions
- `scripts/php-mitigate.sh`      write the stopgap ini drop-in (dry-run by default, `--apply` to write, never restarts for you)
- `scripts/php-fpm-probe.py`     FastCGI client: read the *effective* web-SAPI ini values from a running PHP-FPM (CLI values lie)
- `scripts/cf-origin-lockdown.sh` lock the origin firewall (ufw) to Cloudflare ranges, closing the direct-IP bypass (dry-run default, `--apply` to enforce)
- `scripts/php-hunt.sh`          read-only detection sweep: segfaults, odd child processes, webroot changes, session artefacts
- `scripts/php-recovery-check.sh` read-only: lists every temporary measure still on the host and prints the post-patch checklist (remove blocks, test uploads)
- `reference/facts.md`           what is confirmed vs. unverified, timeline, sources (re-verify, see step 1)
- `reference/internals.md`       how rfc1867 + session.upload_progress work, what each ini knob really does and does not do
- `reference/mitigations.md`     edge/WAF/nginx/Apache/Cloudflare/ModSecurity snippets, per-SAPI ini placement
- `reference/patching.md`        upgrade paths per distro, Docker, shared hosting
- `reference/eol.md`             fixing EOL PHP (7.4 / 8.0 / 8.1): vendor status table, decision table, and four routes with commands
- `scripts/php-eol-source-build.sh` build a fixed 7.4 / 8.0 / 8.1 from PHP's backport branch into its own prefix (dry-run default, `--build` to run)
- `reference/detection.md`       log patterns, EDR rules, IOCs
- `templates/`                   drop-in files used by the scripts and references

## Hard rules (read before doing anything)

1. **Never download, build, or execute any PoC / exploit for these CVEs**, even "for testing",
   even in Docker. Circulating PoC archives are untrusted and have been flagged as potentially
   hostile. Verification is done by version checks and config probes only.
2. **Read-only first.** Inventory and hunt scripts change nothing. Mitigation writes a single
   new ini file and only with `--apply`. Patching is done by the host's package manager.
3. **Confirm before changing anything on a host**: show the user the exact file and restart
   command, then wait. Reloading PHP-FPM / Apache is a service restart.
4. **One host or container at a time.** Report per host. Do not run anything against hosts
   the user has not named.
5. **CLI PHP is not the web PHP.** Versions and ini values must be taken from the SAPI that
   serves traffic (php-fpm, mod_php, php-cgi). Use the probe for FPM. Long-lived PHP processes
   (Octane, Reverb, queue workers, Horizon, supervisor daemons) are web-facing PHP too, and a
   package upgrade does not restart them.
6. Treat everything in `reference/facts.md` as a snapshot. Re-verify against php.net first.
7. **Inventory executes every `php*` binary it finds** (`php -v`) to read versions. On a host
   you already suspect is compromised, run it only after confirming the binaries belong to the
   package manager (`dpkg -S` / `rpm -qf`), or skip inventory and go straight to isolation.

## Remote hosts (the usual case: Claude runs locally, PHP runs on a server)

Nothing needs to be installed on the server. Drive it over SSH from the local session, one host
at a time, using the user's existing key-based access. Ask for the SSH target (`user@host`,
port, jump host) and whether `sudo` is passwordless; if sudo needs a password, give the user the
command to run themselves instead of sending passwords through the agent.

    # 1. copy the scripts and templates to a private dir on the host
    ssh user@host 'mkdir -p -m 700 ~/php2shell-defense'
    scp -r scripts templates user@host:~/php2shell-defense/
    # 2. run read-only steps, capture output locally
    ssh user@host 'sudo ~/php2shell-defense/scripts/php-inventory.sh --docker'
    ssh user@host 'sudo ~/php2shell-defense/scripts/php-mitigate.sh'            # dry-run
    # 3. after the user approves: apply, restart, verify
    ssh user@host 'sudo ~/php2shell-defense/scripts/php-mitigate.sh --apply'
    ssh user@host 'sudo systemctl restart php8.3-fpm'
    ssh user@host 'sudo python3 -I ~/php2shell-defense/scripts/php-fpm-probe.py --socket /run/php/php8.3-fpm.sock'
    ssh user@host 'sudo ~/php2shell-defense/scripts/php-hunt.sh --webroot /var/www/html --days 3'
    # 4. clean up
    ssh user@host 'rm -rf ~/php2shell-defense'

Rules that still apply over SSH: show the dry-run and the exact command before any `--apply` or
restart, never pass `-o StrictHostKeyChecking=no`, never store credentials, and never run the
firewall lockdown without first confirming the SSH port you are connected on is the one it keeps
open. For many hosts, repeat per host and report per host; do not loop blindly.

Docker on the remote host: `php-inventory.sh --docker` already covers containers. For the probe
inside an official `php:*` image see `reference/mitigations.md`.

## Workflow

### 1. Re-verify the facts (2 minutes, do not skip)
Fetch the official sources before giving any advice; follow-up releases or new workarounds may
have landed since `reference/facts.md` was updated (2026-10-21 13:45 UTC):
- https://www.php.net/ (news) and https://www.php.net/releases/index.php?json&version=8.3
  (replace with each branch: 8.2, 8.4, 8.5). The JSON `version` field is the latest release
  of that branch. Fixed versions are 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12; the JSON can lag the
  news page by minutes, so trust the news page if they disagree.
- The two advisories: GHSA-w8hw-w9fx-j79w (CVE-2026-109618) and GHSA-6wmf-4rv5-p3rp
  (CVE-2026-109619) at https://github.com/php/php-src/security/advisories.
Tell the user what is confirmed. `scripts/php-check-release.sh` does the php.net part for you.

### 2. Inventory (read-only)

    scripts/php-inventory.sh            # host
    scripts/php-inventory.sh --docker   # also inspect running containers

For each PHP found it prints: binary, SAPI, version, verdict from php.net, ini scan dir, and the
knobs that matter (`session.upload_progress.enabled`, `memory_limit`, `post_max_size`,
`fatal_error_backtraces` on 8.5, `session.use_strict_mode`, `enable_post_data_reading`), plus the
long-running PHP processes (queue workers, Horizon, Octane, Reverb, supervisor) that will need a
manual restart after the patch. mod_php is the highest-risk SAPI per PHP; say so if you find it. Ask the user about hosts you cannot reach (shared
hosting, PaaS, managed WordPress): they must ask the provider for the patch date.

Classify every PHP instance and decide the path with the user:
- **A: supported branch (8.2-8.5) and fix released** -> patch now (step 5). Ask how long the
  patch will take (package not yet in the distro, change window, image rebuild, tests). If the
  answer is more than about an hour, mitigate first (step 3), then patch.
- **B: supported branch, fix not yet released** -> mitigate now (step 3), patch the moment it ships.
- **C: EOL (8.1 and older)** -> no PHP release, but fixes exist: vendor packages (Ubuntu 22.04,
  Ubuntu Pro ESM, deb.sury.org for jammy/noble, RHEL, Debian LTS), PHP's own source backport
  branches, a container on a supported PHP, or an OS upgrade. Mitigate first, then walk the
  decision table in `reference/eol.md` with the user and run the chosen route. Do not stop at
  "EOL, cannot patch"; that is only true for PHP older than 7.4.
- **D: internet-unreachable (internal tooling, cron-only CLI)** -> lower priority, still patch.

Patching is the fix. Mitigation is what keeps the host alive until the patch lands. Do both
whenever the patch is not immediate.

### 3. Mitigate (stopgap, not a fix)

Offer the ladder below, weakest to strongest, and let the user pick how far to go. Each rung is
applied only after the user approves the exact change, and each rung breaks more:
1. **Config:** the ini drop-in (below). Keeps everything working. Covers the upload-progress path only.
2. **Edge block:** reject `multipart/form-data` except on allow-listed upload paths, at nginx / Apache / Traefik / the CDN WAF (`templates/`, `reference/mitigations.md`). Covers both reported paths. Breaks uploads elsewhere.
3. **Firewall / Cloudflare:** close the origin to the CDN's IP ranges (`scripts/cf-origin-lockdown.sh`) so the edge block cannot be bypassed. Breaks direct access.
4. **Take PHP-FPM offline:** stop the service, serve a static maintenance page, or `return 503` for every non-GET. Nothing else viable, or the host is EOL and exposed. Breaks the site until patched.

Say which rung you recommend and why, in one line, then wait.

Every rung you apply is a debt to collect after the patch. Name every file you create with
`php2shell` in it (the templates already are) so `scripts/php-recovery-check.sh` can find it
later, and before you finish, ask the user which URLs take uploads or multipart posts on each
site and write that list into the report. Rung 2 silently breaks those until it is removed.


    scripts/php-mitigate.sh             # dry-run: shows what would be written where
    scripts/php-mitigate.sh --apply     # writes templates/zzz-php2shell-mitigation.ini into each conf.d

The drop-in sets `session.upload_progress.enabled=0` (confirmed CVE-2026-109619 path),
`memory_limit=-1` (removes the controllable OOM of CVE-2026-109618; pair with a cgroup or
container memory limit, never `RLIMIT_AS`), `fatal_error_backtraces=0` (8.5 only) and
`session.use_strict_mode=1` (hygiene). Explain honestly, in PHP's words: these reduce exposure to
specific paths and do not make the install safe. They must load before request parsing
(php.ini, conf.d, pool `php_admin_*`); `.user.ini` and `ini_set()` do not count. For FPM,
`php_admin_value[memory_limit] = -1` in the pool is stronger than the drop-in. Also recommend a
low `post_max_size` and body/part/header limits at the proxy (`reference/mitigations.md`).

Print the restart command for the user; do not run it unless they say so. PHP says restart
every worker.

**Behind Cloudflare or another CDN:** attackers hit the origin IP directly, bypassing every WAF
rule. Close the origin to the CDN's ranges with `scripts/cf-origin-lockdown.sh` (dry-run first).
If you also close HTTP, the CDN SSL mode must be **Full (strict)**, not Flexible, or the origin
becomes unreachable and HTTP->HTTPS redirects loop. See `reference/mitigations.md`.

### 4. Verify the mitigation on the serving SAPI

    python3 -I scripts/php-fpm-probe.py --socket /run/php/php8.3-fpm.sock
    python3 -I scripts/php-fpm-probe.py --host 127.0.0.1 --port 9000

For mod_php: a one-line `<?php echo ini_get('session.upload_progress.enabled');` in the web
root, curl it, delete it immediately. `php -i` only shows CLI values and is not evidence.

### 5. Patch (the actual fix; do it, do not just describe it)
1. Pick the platform row in `reference/patching.md` and check the package is really available
   (`apt-cache madison php8.x-fpm`, `dnf list --upgrades 'php*'`, `docker pull php:8.x-fpm` then
   `docker run --rm php:8.x-fpm php -v`). If it is not, say so, keep the mitigation, and
   schedule a re-check.
2. Show the user the exact upgrade command, the restart command, and the expected downtime
   (an FPM restart is seconds; a container recreate also needs a proxy reload). Wait for approval.
3. Run it, for **every installed PHP version** on the host, not only the serving one. Restart
   the serving SAPI. For Compose stacks recreate the PHP service, then restart or reload the
   proxy container in the same change (`reference/patching.md`). Then restart every
   long-running PHP process the inventory listed (queue workers, Horizon, Octane, Reverb,
   supervisor daemons): `queue:restart`, `horizon:terminate`, `octane:reload`,
   `supervisorctl restart` (`reference/patching.md`, "Long-running PHP processes"). Laravel
   Forge users: Forge's automatic security updates do not patch PHP; use the PHP tab or SSH.
4. Verify: `scripts/php-check-release.sh` must say PATCHED, and the probe must report the fixed
   version on the serving SAPI. No process may still map a replaced binary (`(deleted)` in
   `/proc/<pid>/exe`; the recovery check lists them). One real HTTP request must succeed end to end.
5. Only then collect the debt: run `scripts/php-recovery-check.sh`, which lists every temporary
   measure still present and prints the checklist. Remove each edge block (nginx / Apache include,
   ModSecurity rule, Traefik router) and any "remove after patch" compose override, reload, then
   **test every upload form and multipart endpoint** from the list gathered in step 3 with a real
   request (`curl -F file=@x ...` or the browser). 403 = a block is still in place, 413 = a size
   limit is now too low. Report which forms were tested. Keep the ini drop-in; it is good hygiene.
   Do not call the host done until this step is complete.
Hosts you cannot patch (shared hosting, PaaS, vendor images): give the user the exact question
to send to the provider and keep the mitigation on until the provider confirms.

### 6. Hunt (read-only)

    scripts/php-hunt.sh --webroot /var/www/html --days 3

Covers: PHP-FPM worker segfaults around multipart POSTs, shells/curl/wget spawned by php-fpm or
httpd, recently changed `.php` / `.htaccess` / `.user.ini` files, webshell signatures, session
files containing `upload_progress_` keys from unknown clients, outbound connections from PHP
workers. Any hit from before the patch time = assume compromise, escalate to IR, do not clean
in place.

### 7. Report
Per host: version before/after, SAPI, mitigation applied (y/n), verification result, hunt
result, remaining risk. Keep it to one table plus bullet points. If any host is EOL and still
internet-facing, say so in the first line.
