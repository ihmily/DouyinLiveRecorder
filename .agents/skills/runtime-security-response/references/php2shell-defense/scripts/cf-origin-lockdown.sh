#!/usr/bin/env bash
# SPDX-License-Identifier: MIT. Provided "as is", no warranty; use at your own risk. See LICENSE.
# Lock the origin firewall so web ports accept traffic only from Cloudflare, closing the
# direct-to-IP bypass that defeats every Cloudflare WAF rule. SSH stays open.
# Uses ufw. Dry-run by default.
# Usage: cf-origin-lockdown.sh [--apply] [--ssh-port N] [--ports "80,443"]
#   --apply        actually reset+build+enable ufw (RESETS existing ufw rules; confirm first)
#   --ssh-port N   SSH port to keep open (default: Port from sshd_config, else 22)
#   --ports LIST   web ports to allow from Cloudflare (default "80,443")
# Fetches live ranges from cloudflare.com/ips-v4 and /ips-v6. Refuses if the lists look short.
set -u
APPLY=0; SSHP=""; WPORTS="80,443"
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1;; --ssh-port) SSHP=$2; shift;; --ports) WPORTS=$2; shift;;
    -h|--help) sed -n '3,10p' "$0"; exit 0;; *) echo "unknown arg $1" >&2; exit 2;;
  esac; shift
done
command -v ufw >/dev/null 2>&1 || { echo "ufw not installed. On RHEL use firewalld; see reference/mitigations.md." >&2; exit 2; }
# Docker publishes ports through its own iptables chains and bypasses ufw entirely.
if command -v docker >/dev/null 2>&1 && docker ps --format '{{.Ports}}' 2>/dev/null | command grep -qE '(0\.0\.0\.0|\[::\]|:):(80|443)->'; then
  echo "WARNING: a container publishes port 80/443. ufw does NOT filter Docker-published ports; this script will not close them." >&2
  if iptables -S DOCKER-USER 2>/dev/null | command grep -qiE 'cloudflare|-j (CLOUDFLARE|CF)'; then
    echo "         A DOCKER-USER rule referencing Cloudflare already exists; verify it with: iptables -L DOCKER-USER -n" >&2
  else
    echo "         Add the allow-list to the DOCKER-USER chain instead (see reference/mitigations.md, Docker section)." >&2
  fi
fi

# SSH port: explicit flag wins; otherwise read sshd_config so a non-default port is not locked out.
sshd_port=$(command grep -hsiE '^[[:space:]]*Port[[:space:]]+[0-9]+' /etc/ssh/sshd_config /etc/ssh/sshd_config.d/*.conf 2>/dev/null | awk '{print $2}' | head -1)
if [ -z "$SSHP" ]; then SSHP=${sshd_port:-22}; fi
echo "$SSHP" | command grep -qE '^[0-9]+$' || { echo "invalid ssh port: $SSHP" >&2; exit 2; }
[ -n "$sshd_port" ] && [ "$sshd_port" != "$SSHP" ] && echo "WARNING: sshd_config says Port $sshd_port but keeping $SSHP open. Lock-out risk; check before --apply." >&2

v4=$(curl -fsS -m 20 https://www.cloudflare.com/ips-v4 | tr -d '\r')
v6=$(curl -fsS -m 20 https://www.cloudflare.com/ips-v6 | tr -d '\r')
n4=$(printf '%s\n' "$v4" | grep -c /); n6=$(printf '%s\n' "$v6" | grep -c /); n=$((n4 + n6))
# Cloudflare publishes ~15 v4 and ~7 v6 ranges. Either list missing or implausibly short => abort.
[ "$n4" -ge 10 ] && [ "$n6" -ge 3 ] || { echo "Cloudflare IP lists look short (v4=$n4 v6=$n6); aborting rather than lock out." >&2; exit 1; }
echo "Cloudflare ranges: $n   SSH port kept open: $SSHP   web ports from CF only: $WPORTS"
if [ "$APPLY" = 0 ]; then
  echo "DRY-RUN. Rules that would be created:"
  echo "  ufw default deny incoming; ufw default allow outgoing"
  echo "  ufw allow $SSHP/tcp"
  printf '  ufw allow from <CF-range> to any port %s proto tcp   (x%s)\n' "$WPORTS" "$n"
  echo "Run again with --apply to enforce. NOTE: --apply resets current ufw rules first."
  exit 0
fi
[ "$(id -u)" = 0 ] || { echo "--apply needs root (sudo)." >&2; exit 2; }
echo "Applying. Existing ufw rules will be reset."
set -e   # any ufw failure from here on aborts instead of reporting a half-built ruleset as active
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
ufw allow "$SSHP"/tcp comment 'ssh' >/dev/null
for ip in $v4 $v6; do ufw allow from "$ip" to any port "$WPORTS" proto tcp comment 'cloudflare' >/dev/null; done
ufw --force enable >/dev/null
set +e
echo "ufw active. cloudflare rules: $(ufw status | grep -c cloudflare)   ssh rules: $(ufw status | grep -c "$SSHP/tcp")"
echo "Verify the site still loads through Cloudflare now. If you later disable the Cloudflare proxy,"
echo "re-open the web ports or the origin becomes unreachable."
