# Patching

Target: the serving SAPI reports a version >= the fixed version for its branch
(official: 8.2.35 / 8.3.36 / 8.4.27 / 8.5.12, released 2026-10-21; `scripts/php-check-release.sh`
checks it). PHP 8.2 reaches EOL on 2026-12-31; plan the next upgrade now.
Always restart/reload the worker processes after the package update; a running FPM master keeps
the old binary mapped until restarted.

## Per platform

| Platform | Command / action | Notes |
|---|---|---|
| Debian / Ubuntu (distro PHP) | `apt update`, then per installed version (`ls /etc/php`): `apt-get install --only-upgrade -o Dpkg::Options::="--force-confold" $(dpkg -l 'php8.3*' \| awk '/^ii/ {print $2}')`, then `systemctl restart php8.x-fpm` (or apache2). `--force-confold` keeps your php.ini and pool files. Upgrade **every** installed version, not only the one serving: an unused `php8.1-fpm` is still a listening service. | Distro backports keep the *same major.minor*; check `apt changelog php8.x-fpm` or the DSA/USN for the CVE IDs rather than the version number. Ubuntu 22.04 ships 8.1, 20.04 ships 7.4: Canonical may backport; check USN. |
| deb.sury.org PPA (Ondřej Surý) | `apt update && apt upgrade` | Fast after upstream release; historically also backports security fixes to EOL branches (7.4, 8.0, 8.1). Best route for EOL on Debian/Ubuntu. |
| RHEL / Alma / Rocky (AppStream) | `dnf update php\*` then `systemctl restart php-fpm httpd` | Red Hat backports under the same version; check RHSA for the CVEs. |
| Remi repository | no update on 21 Oct (confirmed in PHP's advisory) | PHP advises switching to distro packages or building from source. Mitigate meanwhile. |
| Alpine | `apk update && apk upgrade php8x*` then `rc-service php-fpm8x restart` | |
| Official Docker `php:*` images | `docker pull php:8.3-fpm` (tags refresh within hours of release), rebuild, redeploy | Check the running container: `docker exec c php -v`. Pin to the patched tag (e.g. `php:8.3.36-fpm`). |
| Bitnami / custom images | rebuild from updated base, or wait for vendor tag | |
| cPanel (EA4) | `/scripts/update_local_rpm_versions` / wait for EA4 push; `php -v` per `ea-php8x` | cPanel builds its own PHPs; check their changelog. |
| Plesk | Plesk ships its own PHP builds via `plesk installer`; otherwise OS packages | |
| Homebrew (dev) | `brew upgrade php` | dev boxes still matter if they run exposed services |
| Compiled from source | build the fixed tarball, verify sha256 from `https://www.php.net/releases/index.php?json&version=8.x` | |
| Laravel Forge | Forge's automatic security updates **do not patch PHP**. Dashboard: server > PHP tab > version dropdown > **Update PHP X.X** (also repairs the package source), repeat per installed version. SSH: the Debian/Ubuntu command above; first confirm the source file exists (`/etc/apt/sources.list.d/ondrej-php.list` on 22.04/24.04, `php.list` on 26.04) and `apt-cache policy php8.x-fpm` shows the fixed candidate. | PHP comes from `ppa.setup-php.com` (22.04/24.04) or `packages.sury.org` (26.04). Then restart workers: see "Long-running PHP processes". Many servers: a root Recipe, or the Forge API. Forge recommends moving 8.1-and-older sites to a supported version. Source: https://laravel.com/forge/docs/knowledge-base/php-security-release-october-2026 |
| Managed hosting / PaaS (Heroku, Platform.sh, Vercel PHP, Vapor, Kinsta, WP Engine...) | ask provider for patch ETA | Vapor/Lambda custom runtimes must be rebuilt. |

## Long-running PHP processes (restart them, the package upgrade will not)
A package upgrade restarts PHP-FPM (and Apache). It does **not** restart PHP processes started
from the CLI; they keep the old binary mapped until they exit: Laravel queue workers
(`queue:work`), Horizon, Octane (Swoole / FrankenPHP / RoadRunner), Reverb, Symfony Messenger
consumers, anything under supervisor, systemd or pm2. Octane and Reverb serve HTTP from that
old binary. **FrankenPHP embeds its own PHP**: `apt` never patches it. Upgrade the FrankenPHP
binary or image to a release built on a fixed PHP (`frankenphp version` shows the PHP inside).
After every patch:

    php artisan queue:restart          # workers finish the current job and exit; supervisor restarts them
    php artisan horizon:terminate
    php artisan octane:reload          # or octane:stop + start under supervisor
    supervisorctl restart all          # or: systemctl restart <unit>   (covers Reverb, Messenger, custom daemons)
    # per site: run as the site user, in the app directory

Verify: any process whose executable was replaced on disk shows `(deleted)` in `/proc/<pid>/exe`.
`scripts/php-inventory.sh` and `scripts/php-recovery-check.sh` both list them:

    for p in /proc/[0-9]*; do l=$(readlink "$p/exe" 2>/dev/null) || continue; case "$l" in *php*\(deleted\)) echo "${p#/proc/} $l";; esac; done

Empty output = nothing runs the old binary. Containers: a recreated container has no such
processes; a container where you ran `apt upgrade` in place does, and that is one more reason to
rebuild the image instead.

## EOL branches (8.1, 8.0, 7.x, 5.x)
Full treatment with a vendor status table, decision table and commands: `reference/eol.md`.
Summary, in order:
1. Upgrade to 8.2+ now. Most 8.1 apps run on 8.2 with little or no change; 7.4 -> 8.2 needs testing.
2. Distro/vendor backport: Debian LTS/ELTS (Freexian), Ubuntu Pro/ESM, RHEL 7/8 ELS, deb.sury.org, CloudLinux (alt-php). PHP says vendors received the patches in advance; check their trackers for the CVE IDs.
3. Build from PHP's own minimal backport branches for **7.4, 8.0 and 8.1**: `PHP-7.4-CVE-2026-109618-109619`, `PHP-8.0-CVE-2026-109618-109619`, `PHP-8.1-CVE-2026-109618-109619` at https://github.com/php/php-src. Security fix only, no other changes; you own the build.
4. If none of that is possible today: config rung + edge-block multipart + restrict to VPN/allow-list, or take offline. Do not leave EOL PHP internet-facing with no mitigation.

## Containers behind a reverse-proxy container (Docker Compose)
Recreating the PHP/FPM container (to patch the image or add a mitigation mount) gives it a new
container IP. An nginx/proxy container that uses a hostname upstream (`fastcgi_pass app:9000`)
caches the old IP at worker start and returns **502 Bad Gateway** until it re-resolves. After
recreating the app/fpm service, **restart or reload the proxy container** in the same change:

    docker compose -f compose.prod.yml -f compose.override.yml up -d --pull never app queue
    docker restart <nginx-container>   # or: docker compose exec nginx nginx -s reload
    # then confirm the proxy healthcheck and an end-to-end request before declaring done

Use `--pull never` when you only want to add a mount to the existing image, so `pull_policy:
always` services do not fetch a different build mid-mitigation. For a durable ini mitigation in a
stack whose app service mounts no `conf.d`, add a `compose.override.yml` that bind-mounts the
drop-in into each PHP service at `/usr/local/etc/php/conf.d/`, then recreate as above. The real
fix is still bumping the image tag to one built on the patched PHP.

## After patching
1. `scripts/php-check-release.sh` -> PATCHED.
2. Probe the serving SAPI (version served, not CLI).
3. Remove edge blocks; keep the ini drop-in.
4. Run `scripts/php-hunt.sh` once more. A host that was exposed and unpatched while exploitation was active must be treated as possibly compromised regardless of what the hunt shows.
