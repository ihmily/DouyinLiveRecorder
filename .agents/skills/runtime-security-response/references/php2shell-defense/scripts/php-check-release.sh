#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Compare a PHP version against php.net live release data and the PHP2Shell fixed versions.
# Usage: php-check-release.sh [--quiet] [--no-net] [VERSION ...]
#        php-check-release.sh --url https://example.com     (passive: read X-Powered-By/Server headers)
# No VERSION: uses `php -v` from PATH.
# Override the fixed-version table: PHP2SHELL_FIXED="8.5.12 8.4.27 8.3.36 8.2.35"
set -u
FIXED_DEFAULT="8.5.12 8.4.27 8.3.36 8.2.35"   # official, php.net security advisory 2026-10-21
FIXED=${PHP2SHELL_FIXED:-$FIXED_DEFAULT}
QUIET=0; NET=1; URL=""; VERSIONS=""
while [ $# -gt 0 ]; do
  case "$1" in
    --quiet) QUIET=1;; --no-net) NET=0;; --url) URL=$2; shift;;
    -h|--help) sed -n '3,7p' "$0"; exit 0;;
    *) VERSIONS="$VERSIONS $1";;
  esac; shift
done

vge() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -V | head -1)" = "$2" ]; }   # $1 >= $2

if [ -n "$URL" ]; then
  echo "Passive header check for $URL (servers often hide this; absence proves nothing):"
  curl -sSI -m 10 -A 'php2shell-check' "$URL" | command grep -iE '^(server|x-powered-by|http/)' | sed -E 's/^/  /'
  v=$(curl -sSI -m 10 -A 'php2shell-check' "$URL" | command grep -iE '^x-powered-by: *php/' | sed -E 's/.*PHP\/([0-9]+\.[0-9]+\.[0-9]+).*/\1/i' | head -1)
  [ -n "$v" ] && VERSIONS="$v" || { echo "  no PHP version advertised"; exit 0; }
fi
[ -n "$VERSIONS" ] || VERSIONS=$(php -v 2>/dev/null | head -1 | sed -E 's/^PHP ([0-9]+\.[0-9]+\.[0-9]+).*/\1/')
[ -n "$VERSIONS" ] || { echo "no version given and no php in PATH" >&2; exit 2; }

rc=0
for v in $VERSIONS; do
  branch=$(echo "$v" | cut -d. -f1,2)
  fixed=$(for f in $FIXED; do case "$f" in "$branch".*) echo "$f";; esac; done)
  latest=""
  if [ "$NET" = 1 ]; then
    latest=$(curl -sS -m 10 "https://www.php.net/releases/index.php?json&version=$branch" 2>/dev/null | sed -E 's/.*"version":"([0-9.]+)".*/\1/')
    echo "$latest" | command grep -qE '^[0-9]+\.[0-9]+\.[0-9]+$' || latest=""
  fi
  if [ -z "$fixed" ]; then
    verdict="EOL-BRANCH: $branch gets no upstream fix. Mitigate + isolate or migrate (reference/patching.md). Distro backports (Debian/Ubuntu/RHEL/deb.sury.org) may exist: check vendor advisory."
    rc=3
  elif vge "$v" "$fixed"; then
    verdict="PATCHED: $v >= fixed $fixed"
  elif [ -n "$latest" ] && vge "$latest" "$fixed"; then
    verdict="VULNERABLE, FIX AVAILABLE: $v < $fixed (php.net latest for $branch is $latest). Patch now."
    rc=1
  elif [ -n "$latest" ]; then
    verdict="VULNERABLE, FIX NOT YET PUBLISHED on php.net ($branch latest is $latest, fixed version $fixed). Mitigate now, patch when released."
    rc=1
  else
    verdict="VULNERABLE (offline check): $v < fixed version $fixed."
    rc=1
  fi
  if [ "$QUIET" = 1 ]; then echo "$verdict"; else
    echo "PHP $v  branch $branch  php.net latest: ${latest:-unknown}  fixed version: ${fixed:-none}"
    echo "  -> $verdict"
  fi
done
exit $rc
