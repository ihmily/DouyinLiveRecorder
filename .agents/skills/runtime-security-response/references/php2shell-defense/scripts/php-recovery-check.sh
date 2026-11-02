#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Read-only: find every temporary PHP2Shell measure still present on this host and print the
# recovery checklist to run once the patch is verified. Changes nothing.
# Usage: php-recovery-check.sh [--webroot DIR ...]
#   --webroot DIR   extra docroots to scan for .htaccess / .user.ini stopgaps (default: common paths)
# Finds: ini drop-ins, nginx/Apache multipart blocks, ModSecurity rules, Traefik routers,
# systemd MemoryMax overrides, Compose overrides, ufw/DOCKER-USER Cloudflare rules, and processes
# still running a replaced (pre-patch) PHP binary.
set -u
ROOTS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --webroot) ROOTS+=("$2"); shift;;
    -h|--help) sed -n '3,8p' "$0"; exit 0;; *) echo "unknown arg $1" >&2; exit 2;;
  esac; shift
done
[ "${#ROOTS[@]}" -gt 0 ] || for d in /var/www /srv/www /usr/share/nginx/html /home/*/public_html /app /srv/app; do [ -d "$d" ] && ROOTS+=("$d"); done
N=0; found() { N=$((N+1)); printf '  [%d] %s\n' "$N" "$*"; }
G="command grep"

echo "== Temporary PHP2Shell measures still present =="
echo "-- keep after patching (hygiene, PHP recommends it) --"
for f in /etc/php/*/*/conf.d/*php2shell*.ini /etc/php.d/*php2shell*.ini /etc/php*/conf.d/*php2shell*.ini /usr/local/etc/php/conf.d/*php2shell*.ini /etc/opt/remi/php*/php.d/*php2shell*.ini; do
  [ -f "$f" ] && found "ini drop-in: $f"
done
[ "$N" -gt 0 ] || echo "  (none)"
K=$N
echo "-- remove once the serving SAPI reports the fixed version --"
for f in /etc/nginx/snippets/*php2shell* /etc/nginx/conf.d/*php2shell* /etc/apache2/conf-enabled/*php2shell* /etc/httpd/conf.d/*php2shell* /etc/modsecurity/*php2shell* /etc/traefik/*php2shell* /etc/traefik/dynamic/*php2shell*; do
  [ -e "$f" ] && found "edge block file: $f"
done
for c in /etc/nginx /etc/apache2 /etc/httpd; do
  [ -d "$c" ] && while read -r l; do found "edge block include: $l"; done < <($G -rnE 'php2shell' "$c" --include='*.conf' --include='default' --include='*.vhost' 2>/dev/null | $G -vE '^[^:]*php2shell[^:]*:' | $G -E 'include|RewriteCond|multipart' | head -20)
done
for f in /etc/systemd/system/php*-fpm.service.d/*php2shell* /etc/systemd/system/apache2.service.d/*php2shell* /etc/systemd/system/httpd.service.d/*php2shell*; do
  [ -f "$f" ] && found "systemd override (cgroup limit, keep unless it causes OOM kills): $f"
done
for r in "${ROOTS[@]}"; do
  while read -r f; do found "per-dir stopgap: $f"; done < <(command find "$r" -xdev -maxdepth 3 \( -name .htaccess -o -name .user.ini \) -type f -exec $G -lE 'upload_progress|php2shell' {} + 2>/dev/null | head -20)
done
if command -v docker >/dev/null 2>&1; then
  for f in $(docker ps -q 2>/dev/null | xargs -r docker inspect --format '{{index .Config.Labels "com.docker.compose.project.config_files"}}' 2>/dev/null | tr ',' '\n' | sort -u); do
    [ -f "$f" ] && $G -qi 'php2shell' "$f" 2>/dev/null && found "compose override carrying the mitigation mount/limits: $f"
  done
fi
if command -v ufw >/dev/null 2>&1; then
  n=$(ufw status 2>/dev/null | $G -ci cloudflare || true); [ "${n:-0}" -gt 0 ] && found "ufw: $n Cloudflare-only rules (keep if the site stays behind Cloudflare; this is hardening, not a stopgap)"
fi
n=$(iptables -S DOCKER-USER 2>/dev/null | $G -ciE 'cloudflare|-j (CLOUDFLARE|CF)' || true); [ "${n:-0}" -gt 0 ] && found "DOCKER-USER: Cloudflare allow-list present (keep; same reasoning)"
[ "$N" -gt "$K" ] || echo "  (none)"
echo "-- must be empty: processes still running a replaced (pre-patch) PHP binary --"
S=0
for p in /proc/[0-9]*; do
  l=$(readlink "$p/exe" 2>/dev/null) || continue
  case "$l" in *php*"(deleted)") S=$((S+1)); printf '  pid %s: %s  %s\n' "${p#/proc/}" "$l" "$(tr '\0' ' ' < "$p/cmdline" 2>/dev/null | cut -c1-120)";; esac
done
[ "$S" -gt 0 ] && echo "  Restart these (queue:restart, horizon:terminate, octane:reload, supervisorctl restart, systemctl restart)." || echo "  (none)"

cat <<'EOF'

== Recovery checklist (run only after php-check-release.sh says PATCHED and the probe shows the fixed version) ==
1. Confirm the fixed version on the SERVING SAPI, not the CLI: php-fpm-probe.py, or `docker exec c php -v` for official images.
   Patch every installed PHP version (ls /etc/php), and restart long-running PHP: queue workers, Horizon, Octane, Reverb,
   supervisor/systemd daemons. The "must be empty" list above has to be empty.
2. Remove each edge block above (nginx include / Apache include / ModSecurity / Traefik router), `nginx -t` then reload.
   Keep backups outside any included directory.
3. Test every upload form and multipart endpoint from a real browser or curl -F, one per site:
   file upload, image/avatar change, CSV import, media library, contact form with attachment, API multipart endpoints.
   A 403 here means a block is still in place; a 413 means post_max_size or client_max_body_size is now too low.
4. If post_max_size / upload_max_filesize were lowered, restore the values the app needs and restart workers.
5. Keep the ini drop-in (session.upload_progress off, memory_limit -1 with a cgroup limit) unless an app needs upload progress.
6. Remove compose overrides whose header says "remove after patch"; recreate the services and reload the proxy.
7. Run php-hunt.sh once more; a host that was exposed while unpatched stays "possibly compromised" regardless.
8. Record the date, the version served, and which forms were tested, in your change log.
EOF
