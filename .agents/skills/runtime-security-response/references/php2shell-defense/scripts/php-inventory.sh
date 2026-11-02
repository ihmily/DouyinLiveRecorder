#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Read-only inventory of PHP on this host: binaries, SAPIs, versions, exposure-relevant ini values.
# Usage: php-inventory.sh [--docker] [--no-net]
#   --docker   also inspect running containers that contain a php binary
#   --no-net   do not query php.net for latest versions (offline verdict only)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
DOCKER=0; NET=1
for a in "$@"; do case "$a" in --docker) DOCKER=1;; --no-net) NET=0;; -h|--help) sed -n '3,6p' "$0"; exit 0;; esac; done

KEYS="session.upload_progress.enabled memory_limit post_max_size fatal_error_backtraces session.use_strict_mode enable_post_data_reading max_input_nesting_level session.upload_progress.name session.save_path"

say() { printf '%s\n' "$*"; }
hr()  { say "------------------------------------------------------------"; }

# 1. candidate binaries
CANDIDATES=""
for d in /usr/bin /usr/sbin /usr/local/bin /usr/local/sbin /opt/*/bin /opt/plesk/php/*/bin /opt/plesk/php/*/sbin \
         /opt/cpanel/ea-php*/root/usr/bin /opt/cpanel/ea-php*/root/usr/sbin /opt/remi/php*/root/usr/bin /opt/remi/php*/root/usr/sbin \
         /opt/homebrew/opt/php*/bin /opt/homebrew/opt/php*/sbin /usr/local/opt/php*/bin /usr/local/opt/php*/sbin /opt/alt/php*/usr/bin; do
  [ -d "$d" ] || continue
  for f in "$d"/php "$d"/php[0-9]* "$d"/php-fpm "$d"/php-fpm[0-9]* "$d"/php-cgi "$d"/php-cgi[0-9]*; do
    [ -x "$f" ] && [ ! -d "$f" ] && CANDIDATES="$CANDIDATES $(readlink -f "$f" 2>/dev/null || echo "$f")"
  done
done
CANDIDATES=$(printf '%s\n' $CANDIDATES | sort -u)

hr; say "PHP2Shell inventory  host=$(hostname)  date=$(date -u +%Y-%m-%dT%H:%MZ)"; hr
if [ -z "$CANDIDATES" ]; then say "No PHP binaries found in standard locations."; fi

for bin in $CANDIDATES; do
  ver=$("$bin" -v 2>/dev/null | head -1 | sed -E 's/^PHP ([0-9]+\.[0-9]+\.[0-9]+).*/\1/')
  [ -n "$ver" ] || { say "SKIP $bin (not a PHP binary or not runnable)"; continue; }
  sapi=$("$bin" -v 2>/dev/null | head -1 | sed -E 's/.*\(([a-z-]+)\).*/\1/')
  say "BINARY  $bin"
  say "  version: $ver   sapi: $sapi"
  if [ "$NET" = 1 ] && [ -x "$HERE/php-check-release.sh" ]; then
    v=$("$HERE/php-check-release.sh" --quiet "$ver" 2>/dev/null); say "  verdict: ${v:-check failed}"
  fi
  case "$sapi" in
    cli|cgi-fcgi)
      "$bin" --ini 2>/dev/null | sed -E 's/^/  /' | command grep -E 'Loaded|Scan|Additional' || true
      for k in $KEYS; do
        v=$("$bin" -n -d display_errors=0 -r 'echo ini_get($argv[1]) === false ? "(n/a)" : var_export(ini_get($argv[1]), true);' -- "$k" 2>/dev/null)
        e=$("$bin" -d display_errors=0 -r 'echo var_export(ini_get($argv[1]), true);' -- "$k" 2>/dev/null)
        say "  ini  $k = $e   (compiled default: $v)"
      done
      say "  note: these are CLI-effective values. Web SAPI may differ; probe FPM with php-fpm-probe.py."
      ;;
    fpm-fcgi)
      cfg=$("$bin" -tt 2>&1 | command grep -E 'Loaded Configuration|Scan this dir|include=|php_admin_(flag|value)\[(session|enable_post|file_uploads)' | sed -E 's/^.*NOTICE: ?//' | sed -E 's/^/  /')
      [ -n "$cfg" ] && say "$cfg"
      say "  note: php-fpm -tt shows pool overrides only. Effective values: python3 -I $HERE/php-fpm-probe.py --socket <sock>"
      ;;
  esac
  hr
done

# 2. ini files that mention the knobs (any SAPI)
say "INI FILES mentioning the knobs (uncommented lines):"
for d in /etc/php /etc/php.d /etc/php.ini /etc/php-fpm.d /usr/local/etc/php /usr/local/lib/php.ini /opt/plesk/php /opt/cpanel /opt/remi /etc/php[0-9]*; do
  [ -e "$d" ] || continue
  command grep -rEn --include='*.ini' --include='*.conf' '^[[:space:]]*(php_(admin_)?(flag|value)\[)?(session\.upload_progress\.enabled|session\.use_strict_mode|enable_post_data_reading|file_uploads)' "$d" 2>/dev/null | sed -E 's/^/  /'
done
hr

# 3. running web SAPIs
say "RUNNING PROCESSES (php-fpm / php-cgi / apache / nginx / litespeed):"; command -v ps >/dev/null 2>&1 || say "  (ps not installed; check /proc or the container orchestrator)"
ps -eo pid,user,comm,args 2>/dev/null | command grep -E '[p]hp-fpm|[p]hp-cgi|[a]pache2|[h]ttpd|[n]ginx|[l]itespeed|[l]shttpd' | awk '{printf "  %s\n",$0}' | head -40
for ctl in apachectl apache2ctl httpd; do
  if command -v "$ctl" >/dev/null 2>&1; then
    mods=$("$ctl" -M 2>/dev/null | command grep -iE 'php' | tr -s ' ' | sed -E 's/^/  /')
    [ -n "$mods" ] && say "  $ctl -M -> mod_php loaded:" && say "$mods"
  fi
done
say "LONG-RUNNING PHP (CLI-started; a package upgrade does NOT restart these, restart them after patching):"
ps -eo pid,user,args 2>/dev/null | command grep -E '[p]hp.*(queue:work|queue:listen|horizon|octane|reverb|messenger:consume|schedule:work|swoole|roadrunner)|[f]rankenphp|[r]r serve' | awk '{printf "  %s\n",$0}' | head -40
say "PROCESSES STILL MAPPING A REPLACED PHP BINARY (old version in memory):"
for p in /proc/[0-9]*; do l=$(readlink "$p/exe" 2>/dev/null) || continue; case "$l" in *php*"(deleted)") say "  pid ${p#/proc/}: $l";; esac; done
say "LISTENING sockets owned by php (fpm/cgi):"
(ss -lntp 2>/dev/null || netstat -lntp 2>/dev/null) | command grep -E 'php' | sed -E 's/^/  /' | head -20
ls -l /run/php/*.sock /var/run/php/*.sock /run/php-fpm/*.sock /var/run/php-fpm/*.sock 2>/dev/null | sed -E 's/^/  /'
hr

# 4. docker containers
if [ "$DOCKER" = 1 ] && command -v docker >/dev/null 2>&1; then
  say "DOCKER containers with PHP:"
  if docker ps --format '{{.Ports}}' 2>/dev/null | command grep -qE ':(80|443)->'; then
    n=$(iptables -S DOCKER-USER 2>/dev/null | command grep -ciE 'cloudflare|-j (CLOUDFLARE|CF)' || true)
    say "  web ports are Docker-published: ufw does not apply to them. DOCKER-USER Cloudflare rules: ${n:-0} (0 = origin reachable directly)"
  fi
  docker ps --format '{{.ID}} {{.Names}} {{.Image}}' 2>/dev/null | while read -r id name image; do
    v=$(docker exec "$id" sh -c 'command -v php >/dev/null 2>&1 && php -v | head -1' 2>/dev/null | sed -E 's/^PHP ([0-9.]+).*\(([a-z-]+)\).*/\1 \2/')
    [ -n "$v" ] || continue
    say "  $name ($image): $v"
    docker exec "$id" sh -c 'php -r "foreach(explode(\" \",\"session.upload_progress.enabled memory_limit post_max_size fatal_error_backtraces session.use_strict_mode enable_post_data_reading\") as \$k) echo \"      \$k=\",var_export(ini_get(\$k),true),\"\n\";"' 2>/dev/null
    if [ "$NET" = 1 ] && [ -x "$HERE/php-check-release.sh" ]; then
      vd=$("$HERE/php-check-release.sh" --quiet "${v%% *}" 2>/dev/null); say "      verdict: ${vd:-check failed}"
    fi
  done
  hr
fi
say "Done. Next: classify each instance (SKILL.md step 2), then php-mitigate.sh (dry-run)."
