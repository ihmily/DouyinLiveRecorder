# Fixing EOL PHP (8.1, 8.0, 7.4 and older)

PHP ships no release for these branches. It did publish minimal source backports of both fixes:
`PHP-7.4-CVE-2026-109618-109619`, `PHP-8.0-...`, `PHP-8.1-...` on github.com/php/php-src, each a
few commits on top of the last tag (7.4.33, 8.0.30, 8.1.34). Vendors used those to build packages.
Older than 7.4: nothing exists; treat as "migrate or isolate".

Decide with this table, top to bottom. Stop at the first row that applies.

| Your situation | Route | Effort |
|---|---|---|
| Distro package with a vendor fix available (see "Vendor status") | **A: vendor package.** `apt`/`dnf` upgrade, restart workers, probe. | minutes |
| Distro no longer supported by its vendor, but a newer release of the same distro has the fix (Ubuntu 20.04 with Sury, Debian 10) | **D: OS upgrade** in place, then route A. | hours, needs a window |
| Third-party build you cannot refresh (Remi today, a vendor that is slow) | **B: build from PHP's backport branch** into its own prefix, run FPM from there. Or **C** if the app is container-friendly. | 1-2 hours |
| App can run on a supported PHP (8.2+) with little change | **C: containerise or switch** to a supported branch. The only route that also ends the EOL problem. | depends on the app |
| None of the above today | Keep rungs 1-3 of `mitigations.md` on, restrict to VPN/allow-list, plan C. Do not leave it exposed. | |

## Vendor status (checked 2026-10-22, re-check: statuses move)

| Vendor | 7.4 | 8.0 | 8.1 | Source |
|---|---|---|---|---|
| Ubuntu 22.04 (php8.1) | | | **fixed** 8.1.2-1ubuntu2.28, standard repo, USN-8948-1 | ubuntu.com/security/CVE-2026-109618 |
| Ubuntu 20.04 (php7.4) | fixed 7.4.3-4ubuntu2.29+esm5, **Ubuntu Pro (ESM) only** | | not shipped by Ubuntu | same |
| Ubuntu 18.04 / 16.04 | ESM only (php7.2 / php7.0) | | | same |
| deb.sury.org PPA, jammy + noble | 1:7.4.33-31 | 1:8.0.30-25 | 8.1.34-9 (all bumped 2026-10-21 evening; confirm the CVE in `apt changelog`) | ppa.launchpadcontent.net/ondrej/php |
| deb.sury.org PPA, focal (20.04) | **none, PPA dropped focal in June 2025**. Route D or B. | | | |
| Debian 12 bookworm (php8.2) | | | | fixed 8.2.35-1~deb12u1, DLA-4848-1 |
| Debian 11 bullseye (php7.4) | Debian LTS (Freexian): check security-tracker.debian.org for a DLA | | | |
| RHEL 8/9 AppStream (php:7.4 / 8.0 / 8.1 streams) | Red Hat backports under the same version; check access.redhat.com/security/cve/CVE-2026-109618 for the RHSA | | | |
| Remi | no update on 21 Oct; PHP advises switching to distro packages or source | | | |
| CloudLinux alt-php, cPanel ea-php, Plesk | vendor changelogs; cPanel/Plesk build their own | | | |

Verify a vendor fix by the CVE id in the changelog, not by the version number: distros keep the old
upstream version and add a revision.

## Route A: vendor package
    apt update && apt install --only-upgrade 'php7.4*'   # or php8.0*, php8.1*
    apt changelog php8.1-fpm | grep -m3 CVE-2026          # must list both CVEs
    systemctl restart php8.1-fpm                          # restart, not reload
Then `scripts/php-fpm-probe.py` shows the running version and the mitigations still in place.
`php-check-release.sh` will keep saying EOL-BRANCH; that is correct, the branch is EOL. The
changelog is the evidence. Record it in the report.

Ubuntu Pro (free for up to 5 machines on a personal account): `pro attach <token>`,
`pro enable esm-infra`, then route A.

## Route B: build from PHP's backport branch
Use when no vendor package exists and the OS cannot be upgraded today. Builds a second PHP under
`/opt/php-X.Y-php2shell`, runs FPM from there with the existing pool, and leaves the packaged PHP
untouched so rollback is one `systemctl` command.

    scripts/php-eol-source-build.sh --branch 8.1           # dry-run: shows configure line and deps
    scripts/php-eol-source-build.sh --branch 8.1 --build   # 5-20 min

What it does: downloads the branch tarball from GitHub, `buildconf`, `configure` with the host's own
options (`php-config --configure-options`, prefix rewritten) so the same extensions can load,
`make`, `make install` into the prefix. Pass `--opts ""` for a minimal FPM-only build if the
distro's option list will not configure (missing `-dev` packages are the usual reason; install
them or drop that extension from `--opts`).

Extensions: distro PHP loads them as shared modules from `extension_dir` (`php -i | grep
extension_dir`). A build from the same branch with the same flags (NTS, no debug) has the same
ABI (`PHP_API` 20210902 for 8.1), so the distro's `.so` files load. If `PREFIX/bin/php -m`
shows them with no warnings, keep `extension_dir` pointing at the distro directory in the copied
ini. If it warns, build the extension too (`pecl` against `PREFIX/bin/phpize`) or drop it.

Wire it in (Debian layout shown):

    P=/opt/php-8.1-php2shell
    cp /etc/php/8.1/fpm/php.ini $P/etc/php.ini
    cp /etc/php/8.1/fpm/conf.d/*.ini $P/etc/conf.d/
    cp /etc/php/8.1/fpm/pool.d/www.conf $P/etc/php-fpm.d/www.conf
    sed -i 's#^listen = .*#listen = /run/php/php8.1-fpm-fixed.sock#' $P/etc/php-fpm.d/www.conf
    $P/sbin/php-fpm -t -y $P/etc/php-fpm.conf

`/etc/systemd/system/php8.1-fpm-fixed.service`:

    [Unit]
    Description=PHP 8.1 FPM (PHP2Shell source backport)
    After=network.target
    [Service]
    Type=notify
    ExecStart=/opt/php-8.1-php2shell/sbin/php-fpm --nodaemonize --fpm-config /opt/php-8.1-php2shell/etc/php-fpm.conf
    ExecReload=/bin/kill -USR2 $MAINPID
    MemoryMax=600M
    [Install]
    WantedBy=multi-user.target

    systemctl daemon-reload && systemctl enable --now php8.1-fpm-fixed
    python3 -I scripts/php-fpm-probe.py --socket /run/php/php8.1-fpm-fixed.sock
    # The backport branch keeps the 8.1.34 version string. Proof of the fix is the build date in
    # `PREFIX/bin/php -v` (after 2026-10-21) and the branch name in the build log, not the version.
    # switch nginx: fastcgi_pass unix:/run/php/php8.1-fpm-fixed.sock;  then nginx -t && nginx -s reload
    # one real request, then: systemctl disable --now php8.1-fpm

Rollback: point `fastcgi_pass` back, `systemctl start php8.1-fpm`, reload nginx.

Caveats: you now own this build. No package manager will update it. Put a note in the report
and a calendar reminder; the goal is still route C. `apt upgrade` will not touch `/opt`, but a
later distro PHP upgrade will not fix this copy either.

## Route C: containerise on a supported PHP
Keep the OS, move the app into `php:8.3-fpm` (or your own image on it) next to the existing web
server. For most 8.1 apps the code runs on 8.3 unchanged; 7.4 apps need testing (Composer
`platform` checks, deprecated dynamic properties, `${}` interpolation). Sequence:

1. `docker run --rm -v /var/www/site:/app -w /app php:8.3-cli php -l` on the codebase, then
   `composer check-platform-reqs` inside the same image.
2. Build an image: `FROM php:8.3-fpm`, `docker-php-ext-install` the extensions `php -m` lists on
   the host, copy the ini drop-in into `/usr/local/etc/php/conf.d/`.
3. Run it with the site bind-mounted, `-p 127.0.0.1:9000:9000`, pool user matching the file owner.
4. Switch `fastcgi_pass` to `127.0.0.1:9000`, reload nginx, test uploads and the admin area.
5. Stop the host FPM. Keep the ini drop-in. `reference/patching.md` has the Compose notes
   (proxy reload after recreate).

## Route D: OS upgrade
Ubuntu 20.04 to 22.04: `do-release-upgrade` (needs a console or a tmux session, 30-90 min,
reboot). After it, `php8.1` comes from Ubuntu's own repo at 8.1.2-1ubuntu2.28 (fixed) or from the
Sury PPA at 8.1.34-9 if you re-add `ppa:ondrej/php` for jammy. Snapshot the VM first. Expect the
Sury sources to be disabled by the upgrader; re-add them, `apt update`, then route A.

## After any route
1. Probe the serving SAPI: version and the ini values.
2. `scripts/php-recovery-check.sh`, remove edge blocks, test every upload form.
3. Keep the ini drop-in. Keep the cgroup limit.
4. Write down which route you took and when you will leave the EOL branch for good.
