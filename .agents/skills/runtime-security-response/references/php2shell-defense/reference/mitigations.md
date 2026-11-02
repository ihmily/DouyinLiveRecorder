# Mitigations (stopgaps; the fix is the PHP update)

PHP's own words: "There are no complete mitigations, updating is the only safe choice." Everything
below reduces exposure to specific paths. Use it while the patch is in flight, not instead of it.

Ladder, weakest to strongest. Each rung breaks more. Combine rungs; keep rung 1 after patching.
1. **Config** (`scripts/php-mitigate.sh`, the drop-in below). Keeps everything working.
   - `session.upload_progress.enabled=0`: closes the confirmed session path of CVE-2026-109619.
   - `memory_limit=-1`: removes the controllable OOM of CVE-2026-109618. Pair with a cgroup or
     container memory limit. Never `RLIMIT_AS`/`RLIMIT_DATA`.
   - `fatal_error_backtraces=0`: PHP 8.5 only, closes the confirmed mod_php producer.
   - `post_max_size` low, `upload_max_filesize` below it, `max_input_nesting_level` low. Calif
     reports `post_max_size` can be bypassed in some configurations and that the memory pressure
     can come from bodies under it: a speed bump, not a gate. Enforce size at the proxy too.
   - `session.use_strict_mode=1`: hygiene, not in PHP's list.
   These must apply **before request parsing**: php.ini, conf.d, FPM pool `php_admin_*`, Apache
   server config. **Not `ini_set()`, not FPM `.user.ini`.** Restart every worker afterwards.
   Prefer `php_admin_value` for `memory_limit` so no app or pool setting can put a finite limit back.
2. **Edge block**: reject `multipart/form-data` except allow-listed upload paths and/or trusted
   client IPs (`templates/nginx-block-multipart.conf`, `apache-block-multipart.conf`,
   `traefik-block-multipart.yml`, `modsecurity-php2shell.conf`). Removes the multipart OOM trigger
   and the upload-progress path. Also enforce decoded body size, part count, headers per part and
   nesting at the proxy, including for requests without Content-Length. Breaks uploads elsewhere.
3. **Firewall / Cloudflare**: close the origin to the CDN's IP ranges
   (`scripts/cf-origin-lockdown.sh`) so rung 2 cannot be bypassed. Breaks direct access.
4. **Take PHP-FPM offline**: stop the service and serve a static maintenance page, or nginx
   `if ($request_method !~ ^(GET|HEAD)$) { return 503; }`. Built-in CMS maintenance modes do NOT
   help (PHP still runs). Breaks the site until patched.

Also useful: `enable_post_data_reading=0` on paths that never take form posts (per-location via
`fastcgi_param PHP_ADMIN_VALUE "enable_post_data_reading=0";` in nginx or `php_admin_flag` in an
Apache `<Location>`), and FPM `pm.max_requests=1` if the fork cost is acceptable.

Things PHP says to fix because they are producers for CVE-2026-109619: invalid or deprecated INI
directives in `.htaccess` / `php_value` / pool config (they raise diagnostics before init;
suppressing them does not help), attacker-reachable fatal errors, and predictable execution
timeouts.

## Where to put the ini lines, per SAPI

| Setup | Place | Restart |
|---|---|---|
| Debian/Ubuntu FPM | `/etc/php/8.x/fpm/conf.d/zzz-php2shell-mitigation.ini` | `systemctl restart php8.x-fpm` |
| Debian/Ubuntu mod_php | `/etc/php/8.x/apache2/conf.d/zzz-...ini` | `systemctl restart apache2` |
| RHEL/Alma/Rocky | `/etc/php.d/zzz-...ini` (Remi SCL: `/etc/opt/remi/php8x/php.d/`) | `systemctl restart php-fpm` / `httpd` |
| Alpine | `/etc/php8x/conf.d/zzz-...ini` | `rc-service php-fpm8x restart` |
| Official Docker image | `/usr/local/etc/php/conf.d/zzz-...ini` (COPY in Dockerfile or bind-mount) | recreate container, then reload the proxy container |
| Official Docker image, verify | the `php:*` image has no python3, so the probe cannot run inside it. CLI and FPM share `/usr/local/etc/php` there (no per-SAPI dirs), so `docker exec c php -r 'echo ini_get("session.upload_progress.enabled");'` is valid evidence for that image only | |
| FPM pool (preferred for memory_limit) | `php_admin_flag[session.upload_progress.enabled] = off`, `php_admin_value[memory_limit] = -1`, `php_admin_flag[session.use_strict_mode] = on` in `pool.d/www.conf` | restart FPM |
| No root, FPM/CGI | `.user.ini` is **not sufficient** per PHP (applied too late). Ask the host to set it in the pool or php.ini. | |
| No root, mod_php | `.htaccess`: `php_flag session.upload_progress.enabled off`, `php_value memory_limit -1` (needs `AllowOverride Options`; a 500 means not allowed, remove). mod_php applies this before startup, so it does take effect. Make sure every directive there is valid: an invalid one is itself a CVE-2026-109619 producer. | immediate |
| cPanel / Plesk / shared | control panel PHP settings editor, or ask the host | per panel |

PHP says "restart every worker". An FPM `reload` (USR2) recycles workers gracefully and is fine;
a `restart` is the unambiguous choice.

Verify with `python3 -I scripts/php-fpm-probe.py` (FPM) or a temporary `ini_get` file (mod_php).

## Cloudflare and other CDN/WAF
- Keep the hostname **proxied** (orange cloud) and keep managed rules on. Cloudflare shipped
  "Generic Rules - Anomalous Execution" 1-7 to the Managed Free Ruleset and the paid Managed
  Ruleset, default-on from 03:02 UTC 2026-10-21, plus a response-side rule ("Default block for
  High confidence Signatures", Managed Response Firewall, all plans) that blocks a matching
  origin response before it leaves. Paid plans: confirm the Managed Ruleset is deployed in
  **Block** mode, not Log. Review hits under Security > Security Analytics > Events filtered by
  those rule names (ruleset ids: Free `77454fe2d30c4220b5701f6fdfb893ba`, paid Managed
  `efb7b8c949ac4650a09736fc376e9aee`, response rule `afffe22785674c80a31875c848d2242a`); a hit
  before your patch time is an attempt against you. Cloudflare says
  rules may change over the following days; watch the WAF changelog. Source:
  https://blog.cloudflare.com/php-vulnerabilities-waf-protection/
- Add a custom rule as belt-and-braces: `(http.request.method eq "POST" and lower(http.request.headers["content-type"][0]) contains "multipart/form-data" and not http.request.uri.path in {"/wp-admin/async-upload.php" "/upload"})` -> Block.
- Add a body-size rule too; Cloudflare's own upload limit (100 MB on Free) is far above a useful `post_max_size`.
- **SSL mode must be Full (strict)** when you close the origin to HTTP. Cloudflare "Flexible" connects to the origin over plain HTTP, which both defeats a 443-only origin firewall and, on a host that redirects HTTP->HTTPS, causes an infinite redirect loop. Full (strict) makes Cloudflare speak HTTPS to the origin and verify its certificate.
- **Close the origin**: firewall the origin to Cloudflare IP ranges (https://www.cloudflare.com/ips/) or use Authenticated Origin Pulls. Attackers scan origin IPs directly.
- AWS WAF / Azure Front Door / Akamai: equivalent header-match rule on `Content-Type` contains `multipart/form-data`, negative match on upload paths, plus a body-size limit.

## Docker hosts: ufw does not apply
Docker publishes `-p 80:80` through its own iptables chains, ahead of ufw. `ufw` rules, and
`scripts/cf-origin-lockdown.sh`, do not close Docker-published ports. Put the allow-list in the
`DOCKER-USER` chain instead (persist it with iptables-persistent or a boot unit):
```
iptables -N CLOUDFLARE 2>/dev/null
for ip in $(curl -fsS https://www.cloudflare.com/ips-v4); do iptables -A CLOUDFLARE -s "$ip" -j RETURN; done
iptables -A CLOUDFLARE -j DROP
iptables -I DOCKER-USER -p tcp -m multiport --dports 80,443 -m conntrack --ctstate NEW -j CLOUDFLARE
```
`php-inventory.sh --docker` reports whether such a rule exists. Verify from outside the Cloudflare
ranges: `curl -k https://<origin-ip>/` must time out.

Drop-in ordering inside images: the official image scans `conf.d` alphabetically and app images
often ship a `zz-app.ini` that sets `memory_limit`. The skill writes `zzz-php2shell-mitigation.ini`
so it loads last, and warns if a later file still sets a knob. Always re-read the effective value
after recreating the container.

Backups: never leave a backup copy inside a directory nginx or Apache includes with a glob
(`sites-enabled/`, `conf.d/`). The copy is loaded too and `nginx -t` fails with a duplicate
server. Put backups under `/root/php2shell-backups/`.

## Kubernetes / ingress-nginx
Server snippet on the Ingress (if snippets are allowed):
```
nginx.ingress.kubernetes.io/server-snippet: |
  if ($http_content_type ~* "multipart/form-data") { return 403; }
```
Plus `nginx.ingress.kubernetes.io/proxy-body-size: "8m"`. Pod memory limits are the cgroup
boundary PHP recommends alongside `memory_limit=-1`. Or a NetworkPolicy restricting ingress to
the ingress controller only, then the block above.

## Things that do not help
- Updating WordPress/Laravel/Composer packages. The bugs are below them.
- `disable_functions`, `open_basedir`: post-exploitation hardening at best; the UAF gives native code execution in the worker.
- `display_errors=0`, `error_reporting`, `@`: hiding a diagnostic does not stop it touching stale state.
- Hiding `X-Powered-By` (`expose_php=0`): fine hygiene, zero effect on exploitability.
- Rate limiting alone: it raises the number of attempts, not the outcome.
- `RLIMIT_AS` / `RLIMIT_DATA` (`ulimit -v`, systemd `LimitAS`): actively harmful, they cause the allocation failure that triggers CVE-2026-109618.
