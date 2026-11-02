#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Write the PHP2Shell stopgap ini drop-in into every PHP conf.d scan directory found.
# Dry-run by default. Never reloads services.
# Usage: php-mitigate.sh [--apply] [--dir DIR ...] [--no-strict] [--keep-memory-limit]
#   --apply      actually write files (creates <dir>/zzz-php2shell-mitigation.ini; backs up if it exists)
#   --dir DIR    only use these conf.d directories (repeatable)
#   --no-strict  omit session.use_strict_mode=1 (only if an app is known to set its own session IDs)
#   --keep-memory-limit  omit memory_limit=-1 (if you cannot add a cgroup/container memory limit)
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
TPL="$HERE/../templates/zzz-php2shell-mitigation.ini"
NAME=zzz-php2shell-mitigation.ini   # sorts after any zz-*.ini an image or distro may ship
APPLY=0; STRICT=1; MEM=1; DIRS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1;; --no-strict) STRICT=0;; --keep-memory-limit) MEM=0;; --dir) DIRS="$DIRS $2"; shift;;
    -h|--help) sed -n '3,9p' "$0"; exit 0;; *) echo "unknown arg $1" >&2; exit 2;;
  esac; shift
done
[ -r "$TPL" ] || { echo "template missing: $TPL" >&2; exit 2; }
content=$(command cat "$TPL")
[ "$STRICT" = 1 ] || content=$(printf '%s\n' "$content" | command grep -v 'use_strict_mode' | command grep -v 'attacker-supplied session')
[ "$MEM" = 1 ] || content=$(printf '%s\n' "$content" | command grep -vE '^memory_limit|out-of-memory that|container memory limit')

if [ -z "$DIRS" ]; then
  for d in /etc/php/*/fpm/conf.d /etc/php/*/apache2/conf.d /etc/php/*/cgi/conf.d /etc/php/*/litespeed/conf.d \
           /etc/php.d /etc/php[0-9]*/conf.d /usr/local/etc/php/conf.d /etc/opt/remi/php*/php.d /opt/plesk/php/*/etc/php.d \
           /opt/cpanel/ea-php*/root/etc/php.d /opt/alt/php*/etc/php.d /opt/homebrew/etc/php/*/conf.d /usr/local/etc/php/*/conf.d; do
    [ -d "$d" ] && DIRS="$DIRS $d"
  done
  # php-fpm only, not the CLI: the CLI scan dir is not the serving SAPI
  if command -v php-fpm >/dev/null 2>&1; then
    s=$(php-fpm --ini 2>/dev/null | sed -nE 's/^Scan this dir for additional \.ini files => *//p')
    [ -n "$s" ] && [ "$s" != "(none)" ] && [ -d "$s" ] && DIRS="$DIRS $s"
  fi
fi
DIRS=$(printf '%s\n' $DIRS | sort -u)
[ -n "$DIRS" ] || { echo "No conf.d scan directory found. Set it manually: --dir /path/to/conf.d, or add the two lines from $TPL to php.ini." >&2; exit 1; }

echo "Mode: $([ $APPLY = 1 ] && echo APPLY || echo DRY-RUN)   file: $NAME"
echo "Content:"; printf '%s\n' "$content" | sed 's/^/  | /'; echo
warn_later() { for o in $(ls "$1" 2>/dev/null | awk -v n="$NAME" '$0 > n'); do command grep -lE '^(session\.upload_progress\.enabled|memory_limit|fatal_error_backtraces)' "$1/$o" >/dev/null 2>&1 && echo "WARN    $1/$o loads after $NAME and sets a mitigation knob; it wins. Edit it or rename this drop-in."; done; }
for d in $DIRS; do
  t="$d/$NAME"
  warn_later "$d"
  if [ -e "$t" ] && [ "$(command cat "$t")" = "$content" ]; then echo "OK      $t already in place"; continue; fi
  if [ $APPLY = 0 ]; then echo "WOULD WRITE $t"; continue; fi
  [ -w "$d" ] || { echo "SKIP    $d not writable (run with sudo?)"; continue; }
  [ -e "$t" ] && cp -p "$t" "$t.bak.$(date +%s)"
  printf '%s\n' "$content" > "$t" && echo "WROTE   $t"
done
echo
echo "Restart the serving SAPI yourself (not done here); PHP says restart every worker. Typical commands:"
echo "  systemctl restart php8.3-fpm       # Debian/Ubuntu, adjust version"
echo "  systemctl restart php-fpm          # RHEL/Alma/Rocky"
echo "  systemctl restart apache2 | httpd  # mod_php"
echo "  docker restart <container>         # or rebuild image with the ini copied into /usr/local/etc/php/conf.d/"
echo "Stronger for FPM: php_admin_value[memory_limit] = -1 in the pool, so no app can restore a finite limit."
echo "Then verify on the web SAPI: python3 -I $HERE/php-fpm-probe.py --socket <sock> | --host 127.0.0.1 --port 9000"
echo "Note: PHP states .user.ini and ini_set() are NOT sufficient for these CVEs; this drop-in is loaded at startup."
