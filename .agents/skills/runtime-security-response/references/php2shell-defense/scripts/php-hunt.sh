#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Read-only detection sweep for PHP2Shell exploitation attempts / post-exploitation.
# Usage: php-hunt.sh [--webroot DIR ...] [--days N] [--log FILE ...] [--sessions DIR]
#   --webroot DIR   web roots to scan for recent changes and webshell patterns (repeatable; default: common paths)
#   --days N        look-back window for file changes (default 3)
#   --log FILE      extra access/error logs (repeatable; common nginx/apache/php-fpm paths are auto-added)
#   --sessions DIR  session.save_path (default: auto from php -r, plus common paths)
# Prints findings only; changes nothing. Any pre-patch hit => treat as incident, do not clean in place.
set -u
DAYS=3; ROOTS=(); LOGS=""; SESS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --webroot) ROOTS+=("$2"); shift;; --days) DAYS=$2; shift;; --log) LOGS="$LOGS $2"; shift;; --sessions) SESS="$SESS $2"; shift;;
    -h|--help) sed -n '3,9p' "$0"; exit 0;; *) echo "unknown arg $1" >&2; exit 2;;
  esac; shift
done
F=0; hit() { F=$((F+1)); printf '  !! %s\n' "$*"; }
sec() { printf '\n== %s ==\n' "$*"; }
G="command grep"

[ "${#ROOTS[@]}" -gt 0 ] || for d in /var/www /srv/www /usr/share/nginx/html /home/*/public_html /var/www/vhosts/*/httpdocs /app /srv/app; do [ -d "$d" ] && ROOTS+=("$d"); done
for f in /var/log/nginx/*access*.log /var/log/apache2/*access*.log /var/log/httpd/*access*log /var/log/nginx/*error*.log /var/log/apache2/*error*.log /var/log/httpd/*error*log \
         /var/log/php*fpm*.log /var/log/php-fpm/*.log /var/log/php/*.log /var/log/php*.log; do [ -f "$f" ] && LOGS="$LOGS $f"; done
LOGS=$(printf '%s\n' $LOGS | sort -u)

sec "1. Worker crashes and OOM / timeout fatals (exploitation attempts leave these first)"
for f in $LOGS; do
  n=$($G -cE 'SIGSEGV|signal 11|SIGBUS|signal 7|SIGABRT|signal 6|exited on signal|Segmentation fault|double free|corrupted' "$f" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] && hit "$n crash lines in $f" && $G -E 'SIGSEGV|signal 11|SIGBUS|SIGABRT|exited on signal|Segmentation fault' "$f" | tail -5 | sed 's/^/     /'
  n=$($G -cE 'Allowed memory size of [0-9]+ bytes exhausted|Out of memory|Maximum execution time of [0-9]+ seconds exceeded' "$f" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] && hit "$n OOM / execution-timeout fatals in $f (the CVE-2026-109618 trigger and the CVE-2026-109619 producer; a burst from one client is an attempt)" && $G -E 'Allowed memory size|Out of memory|Maximum execution time' "$f" | tail -3 | sed 's/^/     /'
done
if command -v journalctl >/dev/null 2>&1; then
  n=$(journalctl -k --since "-${DAYS}d" 2>/dev/null | $G -ciE 'php-fpm.*segfault|php-cgi.*segfault|(httpd|apache2).*segfault' || true)
  [ "${n:-0}" -gt 0 ] && hit "$n kernel segfault entries for php/httpd in last $DAYS days (journalctl -k)"
fi
for f in /var/log/kern.log /var/log/messages /var/log/syslog; do
  [ -f "$f" ] || continue
  n=$($G -ciE '(php-fpm|php-cgi|httpd|apache2).*segfault' "$f" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] && hit "$n segfault lines in $f"
done

sec "2. Multipart POSTs and upload-progress markers in access logs"
echo "  (standard combined log formats do not record Content-Type; add \$content_type / %{Content-Type}i to see multipart traffic)"
for f in $LOGS; do
  n=$($G -ci 'PHP_SESSION_UPLOAD_PROGRESS' "$f" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] && hit "$n lines with PHP_SESSION_UPLOAD_PROGRESS in $f (field name in URL/query; body hits only if body logging is on)"
  n=$($G -ci 'multipart/form-data' "$f" 2>/dev/null || true)
  [ "${n:-0}" -gt 0 ] && echo "  info: $n multipart/form-data lines in $f (review targets that do not accept uploads):" && \
    $G -i 'multipart/form-data' "$f" | awk '{print $7}' | sort | uniq -c | sort -rn | head -10 | sed 's/^/     /'
done

sec "3. Suspicious children of PHP workers / web servers"
if command -v ps >/dev/null 2>&1; then
  while read -r l; do hit "$l"; done < <(ps -eo pid,ppid,user,comm 2>/dev/null | awk 'NR>1{c[$1]=$4; pp[$1]=$2; u[$1]=$3} END{for(p in c){ if(pp[p] in c){ parent=c[pp[p]]; if(parent ~ /php-fpm|php-cgi|httpd|apache2|lsphp|litespeed/ && c[p] ~ /^(sh|bash|dash|zsh|curl|wget|nc|ncat|socat|python[0-9.]*|perl|ruby|base64|chmod|id|whoami|uname|busybox)$/) print "pid "p" ("c[p]", user "u[p]") child of "parent" pid "pp[p]}}}')
  while read -r l; do hit "$l"; done < <(ps -eo pid,user,args 2>/dev/null | $G -E '/dev/tcp/|mkfifo|bash -i|0>&1|base64 -d' | $G -vE 'grep -E|php-hunt' | sed 's/^/cmdline: /')
  echo "  (empty = nothing found right now; point-in-time check, use EDR/auditd/Falco for continuous coverage)"
else
  echo "  ps not available; inspect /proc or use the orchestrator"
fi

sec "4. Outbound connections from PHP workers"
(ss -tnp 2>/dev/null || netstat -tnp 2>/dev/null) | $G -E 'php-fpm|php-cgi|httpd|apache2' | $G -vE ':(3306|5432|6379|11211|9000|9001)\s' | sed 's/^/  /' | head -20

sec "5. Recently changed files in web roots (last $DAYS days)"
for r in "${ROOTS[@]}"; do
  while read -r f; do hit "modified: $f ($(date -r "$f" '+%F %T' 2>/dev/null))"; done < <(command find "$r" -xdev -type f \( -name '*.php' -o -name '*.phtml' -o -name '*.phar' -o -name '.htaccess' -o -name '.user.ini' -o -name '*.ini' \) -mtime "-$DAYS" 2>/dev/null | head -50)
  while read -r f; do hit "php file in upload/cache dir: $f"; done < <(command find "$r" -xdev -type f \( -name '*.php' -o -name '*.phtml' \) \( -path '*/uploads/*' -o -path '*/cache/*' -o -path '*/tmp/*' -o -path '*/media/*' -o -path '*/images/*' \) -not -path '*/vendor/*' -not -path '*/bootstrap/cache/*' -not -path '*/node_modules/*' 2>/dev/null | head -50)
done

sec "6. Webshell signatures in web roots (recent files only)"
for r in "${ROOTS[@]}"; do
  while read -r f; do hit "webshell pattern: $f"; done < <(command find "$r" -xdev -type f \( -name '*.php' -o -name '*.phtml' \) -mtime "-$DAYS" -print0 2>/dev/null | head -z -n 500 | \
    xargs -0 -r grep -lE '(eval|assert|system|passthru|shell_exec|popen|proc_open)[[:space:]]*\([[:space:]]*(base64_decode|gzinflate|str_rot13|strrev|\$_(GET|POST|REQUEST|COOKIE|SERVER))|\$_(GET|POST|REQUEST|COOKIE)\[[^]]+\][[:space:]]*\(' 2>/dev/null)
done

sec "7. Session store: upload-progress artefacts"
[ -n "$SESS" ] || SESS=$(php -r 'echo ini_get("session.save_path");' 2>/dev/null | sed -E 's/^[0-9]+;//')
for d in $(printf '%s\n' $SESS /var/lib/php/sessions /var/lib/php/session /tmp /var/tmp | sort -u); do
  [ -d "$d" ] || continue
  n=$(command find "$d" -maxdepth 1 -type f -name 'sess_*' -mtime "-$DAYS" -print0 2>/dev/null | head -z -n 2000 | xargs -0 -r grep -l 'upload_progress_' 2>/dev/null | wc -l | tr -d ' ')
  [ "${n:-0}" -gt 0 ] && hit "$n session files in $d contain upload_progress_ keys (written by the handler; expected only if your app uses upload progress bars)"
done

sec "8. Persistence: cron and service units changed in last $DAYS days"
while read -r f; do hit "changed: $f"; done < <(command find /etc/cron* /var/spool/cron /etc/systemd/system -xdev -type f -mtime "-$DAYS" 2>/dev/null | head -30)
command -v crontab >/dev/null 2>&1 && for u in www-data apache nginx nobody; do c=$(crontab -l -u "$u" 2>/dev/null | $G -v '^#' | $G -v '^$'); [ -n "$c" ] && hit "crontab for $u:" && printf '%s\n' "$c" | sed 's/^/     /'; done
echo "  (also review new local users and authorized ssh keys by hand; see reference/detection.md)"

sec "SUMMARY"
if [ "$F" -gt 0 ]; then echo "  $F finding(s) above. Correlate timestamps with the patch time. Pre-patch hits => incident response, preserve evidence, do not clean in place."; else echo "  No findings. Patch status still decides exposure; run php-check-release.sh."; fi
