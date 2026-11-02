#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Build a fixed PHP for an EOL branch (7.4, 8.0, 8.1) from PHP's official source backport branch
# PHP-<branch>-CVE-2026-109618-109619, into its own prefix, without touching the packaged PHP.
# Dry-run by default: prints what it would do. --build does it (takes 5-20 minutes).
# Usage: php-eol-source-build.sh [--build] [--branch 8.1] [--prefix DIR] [--opts "configure options"]
#   --branch X.Y   EOL branch to build (default: branch of `php` in PATH if it is 7.4/8.0/8.1)
#   --prefix DIR   install prefix (default /opt/php-X.Y-php2shell)
#   --opts STR     configure options; default: the running PHP's own (`php-config --configure-options`)
#                  with prefix/paths rewritten, so the same extensions can load. Pass "" for a minimal build.
#   --jobs N       make jobs (default: nproc)
# After the build: this installs php-fpm and php under PREFIX. It does NOT replace /usr/sbin/php-fpmX.Y.
# Point a new systemd unit at PREFIX/sbin/php-fpm with the existing pool config, switch the socket,
# verify with php-fpm-probe.py, then disable the old unit. See reference/eol.md for the unit file.
set -u
BUILD=0; BRANCH=""; PREFIX=""; OPTS="__auto__"; JOBS=$(nproc 2>/dev/null || echo 2)
while [ $# -gt 0 ]; do
  case "$1" in
    --build) BUILD=1;; --branch) BRANCH=$2; shift;; --prefix) PREFIX=$2; shift;; --opts) OPTS=$2; shift;; --jobs) JOBS=$2; shift;;
    -h|--help) sed -n '3,14p' "$0"; exit 0;; *) echo "unknown arg $1" >&2; exit 2;;
  esac; shift
done
if [ -z "$BRANCH" ]; then
  BRANCH=$(php -r 'echo PHP_MAJOR_VERSION.".".PHP_MINOR_VERSION;' 2>/dev/null || true)
fi
case "$BRANCH" in 7.4|8.0|8.1) ;; *) echo "branch '$BRANCH' is not 7.4, 8.0 or 8.1. Supported branches get a normal release: use the package manager." >&2; exit 2;; esac
PREFIX=${PREFIX:-/opt/php-$BRANCH-php2shell}
GITBRANCH="PHP-$BRANCH-CVE-2026-109618-109619"
URL="https://codeload.github.com/php/php-src/tar.gz/refs/heads/$GITBRANCH"

# configure options: reuse the host's so extension ABI and ini layout match
if [ "$OPTS" = "__auto__" ]; then
  pc=""; for c in "php-config$BRANCH" php-config; do command -v "$c" >/dev/null 2>&1 && { pc=$c; break; }; done
  if [ -n "$pc" ]; then
    OPTS=$("$pc" --configure-options 2>/dev/null | sed -E "s#--(prefix|with-config-file-path|with-config-file-scan-dir|enable-fpm|with-fpm-user|with-fpm-group|disable-cgi|enable-cgi)(=[^ ]*)?##g; s#--(libdir|datadir|mandir|includedir|program-suffix|sysconfdir|localstatedir|with-layout)=[^ ]*##g; s#--build=[^ ]*##; s#--host=[^ ]*##; s#--with-pear[^ ]*##; s#'[^']*'##g")
    echo "configure options taken from $pc (prefix rewritten to $PREFIX)."
    echo "Distro builds compile most extensions as shared modules; those need the same flags and dev"
    echo "headers. Expect to trim options that fail; the FPM core needs none of them."
  else
    OPTS=""; echo "no php-config found: minimal build (fpm + cli, no optional extensions)."
  fi
fi
OPTS="--prefix=$PREFIX --with-config-file-path=$PREFIX/etc --with-config-file-scan-dir=$PREFIX/etc/conf.d --enable-fpm --with-fpm-user=www-data --with-fpm-group=www-data --disable-cgi $OPTS"

echo "Branch:  $GITBRANCH"
echo "Source:  $URL"
echo "Prefix:  $PREFIX"
echo "Jobs:    $JOBS"
echo "Configure: $OPTS" | fold -s -w 110 | sed '2,$s/^/           /'
if [ "$BUILD" = 0 ]; then
  echo; echo "DRY-RUN. Re-run with --build to download, build and install into $PREFIX."
  echo "Build deps (Debian/Ubuntu): build-essential autoconf bison re2c pkg-config libxml2-dev libsqlite3-dev libssl-dev"
  echo "  plus one -dev package per extension in the configure line (libcurl4-openssl-dev, libonig-dev, libzip-dev, libpng-dev ...)."
  exit 0
fi

for t in gcc make autoconf bison re2c; do command -v "$t" >/dev/null 2>&1 || { echo "missing build tool: $t" >&2; exit 2; }; done
set -e
work=$(mktemp -d /tmp/php-eol-build.XXXXXX)
echo "Downloading to $work ..."
curl -fsSL -m 300 "$URL" | tar -xz -C "$work"
src=$(find "$work" -maxdepth 1 -mindepth 1 -type d | head -1)
cd "$src"
echo "Source version: $(sed -nE 's/^#define PHP_VERSION "([^"]+)"/\1/p' main/php_version.h)"
./buildconf --force >/dev/null
# shellcheck disable=SC2086
./configure $OPTS >"$work/configure.log" 2>&1 || { echo "configure failed; see $work/configure.log (last lines):" >&2; tail -15 "$work/configure.log" >&2; exit 1; }
echo "Building with $JOBS jobs ..."
make -j"$JOBS" >"$work/make.log" 2>&1 || { echo "make failed; see $work/make.log (last lines):" >&2; tail -15 "$work/make.log" >&2; exit 1; }
make install >"$work/install.log" 2>&1
mkdir -p "$PREFIX/etc/conf.d" "$PREFIX/etc/php-fpm.d"
[ -f "$PREFIX/etc/php-fpm.conf" ] || cp "$PREFIX/etc/php-fpm.conf.default" "$PREFIX/etc/php-fpm.conf"
echo
echo "Installed: $("$PREFIX/sbin/php-fpm" -v | head -1)"
echo "           $("$PREFIX/bin/php" -v | head -1)"
echo "Next (reference/eol.md has the full sequence):"
echo "  1. Copy your pool: cp /etc/php/$BRANCH/fpm/pool.d/www.conf $PREFIX/etc/php-fpm.d/  (Debian layout; adjust)"
echo "  2. Copy php.ini + conf.d from the serving SAPI into $PREFIX/etc/ and $PREFIX/etc/conf.d/,"
echo "     keep extension_dir pointing at the distro's extension dir only if the ABI matches ($PREFIX/bin/php -m to check)."
echo "  3. $PREFIX/sbin/php-fpm -t -y $PREFIX/etc/php-fpm.conf"
echo "  4. Install the systemd unit from reference/eol.md, start it, probe the socket, then stop the old unit."
echo "Logs: $work"
