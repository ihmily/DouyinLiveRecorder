# php2shell-defense

A defensive [Claude Code](https://claude.com/claude-code) skill for the October 2026 PHP runtime
RCEs **CVE-2026-109618 / CVE-2026-109619** ("PHP2Shell", CVSS v4.0 9.2). It helps you find every
PHP you run, apply stopgap mitigations, verify them on the SAPI that actually serves traffic,
patch, and look for signs of exploitation.

Fixed in PHP 8.2.35, 8.3.36, 8.4.27 and 8.5.12, released 21 October 2026. One bug is in how PHP
handles running out of memory during request startup; the other lets state from a crashed request
leak into the next request on the same worker. Both run before any application script. No CMS,
framework or application-layer check can protect you. PHP's own advisory says there are no
complete mitigations; everything in this skill except the patch buys time.

**Defensive only.** This skill contains no exploit code and instructs the agent never to fetch,
build or run any proof-of-concept for these CVEs. Verification is by version checks and config
probes, never by detonation.

> **Disclaimer.** This software is provided "as is", without warranty of any kind. The authors
> are not liable for any damage, outage, data loss, lock-out or security incident arising from its
> use. It is a stopgap toolkit written during an active incident, partly before the official
> advisory was published; facts in it may be incomplete or wrong. Read every script before you run
> it, run dry-runs first, and **use it at your own risk**. See [LICENSE](LICENSE).

## What it does

| Script                          | Changes anything?                | What it does                                                                                                                                                                 |
|---------------------------------|----------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| `scripts/php-inventory.sh`      | No                               | Finds every PHP binary, SAPI and container on the host, their versions, and the ini values that matter for this bug. Executes `php -v` on binaries it finds.                 |
| `scripts/php-check-release.sh`  | No                               | Compares a version (or local `php`) against php.net live release data and the fixed-version table. Exit code 0 patched, 1 vulnerable, 3 EOL branch.                          |
| `scripts/php-mitigate.sh` | Only with `--apply` | Writes one ini drop-in with PHP's published workarounds (`session.upload_progress.enabled=0`, `memory_limit=-1`, `fatal_error_backtraces=0` on 8.5) plus `session.use_strict_mode=1` into each PHP `conf.d`. Dry-run by default. Never restarts services. |
| `scripts/php-fpm-probe.py`      | Writes and deletes one temp file | Talks FastCGI to a running PHP-FPM and prints the *effective* version and ini values of the serving SAPI. CLI values can differ and are not evidence.                        |
| `scripts/cf-origin-lockdown.sh` | Only with `--apply`              | Rebuilds the `ufw` ruleset so web ports accept traffic only from Cloudflare IP ranges, keeping SSH open. **Resets existing ufw rules.** Dry-run by default.                  |
| `scripts/php-hunt.sh`           | No                               | Read-only sweep for exploitation signs: worker segfaults, shells spawned by PHP workers, recently changed webroot files, webshell patterns, session artefacts, cron changes. |
| `scripts/php-recovery-check.sh` | No | After the patch: lists every temporary measure still on the host (edge blocks, compose overrides, drop-ins, cgroup limits) and prints the recovery checklist, including testing every upload form. |
| `scripts/php-eol-source-build.sh` | Only with `--build` | For PHP 7.4 / 8.0 / 8.1 with no vendor package: builds PHP's official backport branch into `/opt/php-X.Y-php2shell` with the host's own configure options. Never replaces the packaged PHP; `reference/eol.md` shows how to switch FPM over and back. |

Supporting material:
- `reference/facts.md` what is confirmed vs. unverified, timeline, sources
- `reference/internals.md` how the multipart parser and `session.upload_progress` work, what each ini knob does and does not do
- `reference/mitigations.md` edge rules (nginx, Apache, Traefik, ModSecurity, Cloudflare), per-SAPI ini placement
- `reference/patching.md` upgrade paths per distro, Docker, shared hosting
- `reference/eol.md` fixing EOL PHP 7.4 / 8.0 / 8.1: who ships a fix, which route to take, and the commands for each
- `reference/detection.md` log patterns, auditd/Falco/osquery rules, log queries
- `templates/` the ini drop-in and edge-block configs used above

## Install (on your own machine)

Install the skill where you run Claude Code, not on the server:

    # all projects
    cp -r php2shell-defense ~/.claude/skills/
    # or one project
    cp -r php2shell-defense <repo>/.claude/skills/

Start a new Claude Code session. The skill triggers when you mention PHP2Shell, the CVE IDs, the
October 2026 PHP release, `session.upload_progress`, or ask whether your PHP hosts are exposed.
You can also call it directly with `/php2shell-defense <request>`.

## Prerequisites

On your machine:
- Claude Code, `ssh` and `scp`.
- Key-based SSH access to each server (`ssh user@host` works without typing a password). Put jump
  hosts and non-standard ports in `~/.ssh/config` so the agent can use a plain hostname.

On each server (nothing to install):
- `bash`, `curl`, standard GNU userland. `python3` for the FPM probe (Debian, Ubuntu, RHEL and
  Alpine usually have it; the official `php:*` Docker images do not, see `reference/mitigations.md`).
- `sudo` rights. Passwordless sudo lets the agent run every step; otherwise it shows you the
  commands that need root and asks you to run them.
- `ufw` only if you use `cf-origin-lockdown.sh` (Debian/Ubuntu). RHEL uses firewalld; see the reference.

## How to use

### With Claude Code (normal case)

Open Claude Code on your machine and name the host:

    /php2shell-defense check web-01 (ssh deploy@web-01) for PHP2Shell exposure and mitigate it

The agent then, one host at a time:
1. Re-verifies the advisory on php.net and tells you if anything changed since the skill was written.
2. Copies `scripts/` and `templates/` to `~/php2shell-defense` on the host with `scp`.
3. Runs the read-only inventory over `ssh` and classifies each PHP it finds.
4. Decides the path with you. Patch available and quick: patch now. Patch will take time, or
   no patch for your branch: temporary mitigation first, from a ladder of config change, edge
   block of multipart requests, firewall or Cloudflare origin lockdown, and as a last resort
   taking PHP-FPM offline behind a maintenance page.
5. Shows you every dry-run and the exact command before each step, then waits for your OK.
6. Applies, restarts, and proves each change on the serving SAPI with the FPM probe.
7. Patches: checks the package is really available, shows the upgrade and restart commands and
   the expected downtime, runs them after your OK, restarts the serving SAPI, and re-checks the
   version over FastCGI. Then rolls back the temporary blocks you want removed.
8. Runs the exploitation hunt and gives you a per-host report.
9. Removes `~/php2shell-defense` from the host.

It never applies, reloads or changes firewall rules without showing you first. It never fetches
or runs exploit code. Hosts you cannot SSH into (shared hosting, PaaS) get a checklist to send to
the provider instead.

### Examples

Prompts that trigger the skill, by situation:

    # single server, full response
    /php2shell-defense web-01 (ssh deploy@web-01) runs WordPress on PHP 8.3. Check exposure, mitigate, verify.

    # just want to know if you are affected
    Am I exposed to PHP2Shell? Hosts: ssh ops@app-1, ssh ops@app-2. Read-only, do not change anything yet.

    # Docker Compose stack behind nginx, Cloudflare in front
    /php2shell-defense ssh root@shop. PHP runs in docker compose (service "app"), nginx container in front, site is behind Cloudflare. Mitigate and lock the origin.

    # already patched, want proof and a hunt
    We upgraded php8.3-fpm on ssh admin@api last night. Confirm the serving version is fixed and hunt for exploitation from before the patch.

    # old PHP you cannot upgrade today
    ssh legacy@crm runs PHP 7.4 and cannot be upgraded this week. What can I do right now?

    # no SSH access
    My site is on shared hosting at <provider>. What do I ask them and what can I set myself?

Illustrative session (shortened):

    > /php2shell-defense web-01 (ssh deploy@web-01) runs WordPress on PHP 8.3. Check exposure, mitigate, verify.

    Re-checking php.net: 8.3 latest is 8.3.36 (released today). Fix is available.
    Copying scripts to deploy@web-01:~/php2shell-defense and running the read-only inventory...

    web-01: php-fpm 8.3.35 (fpm-fcgi), socket /run/php/php8.3-fpm.sock
            session.upload_progress.enabled=1  session.use_strict_mode=0
            verdict: VULNERABLE, FIX AVAILABLE (8.3.35 < 8.3.36). Class A: patch now.

    Dry-run of the stopgap (to apply while you schedule the patch):
      WOULD WRITE /etc/php/8.3/fpm/conf.d/zzz-php2shell-mitigation.ini
      WOULD WRITE /etc/php/8.3/cli/conf.d/zzz-php2shell-mitigation.ini
    Restart needed afterwards (PHP: restart every worker): sudo systemctl restart php8.3-fpm
    Apply and restart? (y/n)

    > y

    Written and restarted. FPM probe over the socket:
      PHP 8.3.35 (fpm-fcgi)
      session.upload_progress.enabled = '0'  OK
      session.use_strict_mode = '1'  OK
    Mitigation is live on the serving SAPI. This closes the upload-progress path only; patch
    for full coverage. For Ubuntu with distro PHP:
      sudo apt update && sudo apt install --only-upgrade 'php8.3*' && sudo systemctl restart php8.3-fpm
    Run it now? (y/n)

    > y

    Patched. Probe now reports PHP 8.3.36 (fpm-fcgi). Running the hunt (last 3 days)...
      No crash lines in php8.3-fpm.log. No shells under php-fpm. No webroot changes.
      0 findings.
    Report for web-01: 8.3.35 -> 8.3.36, mitigated and patched, verified over FastCGI,
    hunt clean. Remaining risk: host was reachable and unpatched while exploitation was
    active; keep the drop-in, watch logs for a week. Removed ~/php2shell-defense from the host.

### Without Claude, from your machine over SSH

Same sequence by hand. Replace `user@host`, the PHP version and the webroot:

    H=user@host
    ssh $H 'mkdir -p -m 700 ~/php2shell-defense'
    scp -r scripts templates $H:~/php2shell-defense/
    # 1. is the fix out for the host's branch?
    ssh $H '~/php2shell-defense/scripts/php-check-release.sh'
    # 2. what PHP runs there and how is it configured?
    ssh $H 'sudo ~/php2shell-defense/scripts/php-inventory.sh --docker'
    # 3. stopgap mitigation: dry-run, read it, apply, restart
    ssh $H 'sudo ~/php2shell-defense/scripts/php-mitigate.sh'
    ssh $H 'sudo ~/php2shell-defense/scripts/php-mitigate.sh --apply'
    ssh $H 'sudo systemctl restart php8.3-fpm'
    # 4. prove it on the serving SAPI (CLI values are not evidence)
    ssh $H 'sudo python3 -I ~/php2shell-defense/scripts/php-fpm-probe.py --socket /run/php/php8.3-fpm.sock'
    # 5. behind Cloudflare? close the direct-to-origin bypass (dry-run first; resets ufw)
    ssh $H 'sudo ~/php2shell-defense/scripts/cf-origin-lockdown.sh'
    ssh $H 'sudo ~/php2shell-defense/scripts/cf-origin-lockdown.sh --apply'
    # 6. patch (reference/patching.md), then repeat 1 and 4
    # 7. collect the temporary measures: list them, remove the edge blocks, test every upload form
    ssh $H 'sudo ~/php2shell-defense/scripts/php-recovery-check.sh'
    # 8. look for exploitation evidence
    ssh $H 'sudo ~/php2shell-defense/scripts/php-hunt.sh --webroot /var/www/html --days 3'
    # 9. clean up
    ssh $H 'rm -rf ~/php2shell-defense'

Every script prints `--help`.

### On the server itself

Already logged in on the host? Copy the folder there and run the same commands without the
`ssh $H` prefix.

## What it changes on your host

Nothing, unless you pass `--apply`:
- `php-mitigate.sh --apply` creates `zzz-php2shell-mitigation.ini` in each PHP `conf.d` it finds
  (backs up an existing copy). It does not restart anything; you do.
- `cf-origin-lockdown.sh --apply` runs `ufw --force reset`, sets default deny incoming, allows the
  SSH port (from `sshd_config` or `--ssh-port`), allows web ports from Cloudflare ranges only,
  then enables ufw. If the SSH port is wrong, or you later turn off the Cloudflare proxy, you lock
  yourself out. Run the dry-run and read it first.
- `php-fpm-probe.py` writes a small PHP file to a private temp dir (or a path you give that must
  not exist yet), asks FPM to run it, and deletes it.

Edge templates in `templates/` block all `multipart/form-data` requests except an allow-list of
upload paths. They break file uploads and multipart forms everywhere else until you edit the
allow-list. Nothing installs them for you.

## Limitations
- Facts and fixed versions follow PHP's security advisory of 21 October 2026. The skill still
  tells the agent to re-verify on php.net first, and the release check reads php.net live, so
  follow-up releases are picked up without an edit.
- The ini drop-in covers the paths PHP has published workarounds for. PHP states these do not
  make an installation safe. Only the patch does.
- `memory_limit=-1` in the drop-in removes a safety net against runaway scripts. PHP recommends it
  together with a container or cgroup memory limit. Pass `--keep-memory-limit` to leave it out.
- The hunt is a point-in-time check. A clean result does not prove a host was not compromised.
- Scripts were tested in Docker (`php:8.3-fpm`, Debian php-fpm 8.4, nginx, httpd, ubuntu with
  ufw), not on every distro or control panel they mention.

## Authorization
Run this only against hosts you own or are explicitly authorized to administer.

## License
MIT. See [LICENSE](LICENSE). No warranty, no liability, use at your own risk.
