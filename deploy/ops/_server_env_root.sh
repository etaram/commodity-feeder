#!/bin/sh
# Runs as root on the server (called by server-env.sh). Reads KEY=VALUE lines on stdin and writes them into the .env.
set -eu
E=/opt/sinder/repo/deploy/.env; umask 077
cp -p "$E" "$E.bak-$(date -u +%Y%m%dT%H%M%SZ)"; chmod 600 "$E".bak-*
N=$(mktemp); cat > "$N"
cut -d= -f1 "$N" | while read -r k; do grep -vE "^$k=" "$E" > "$E.tmp" || true; cat "$E.tmp" > "$E"; rm -f "$E.tmp"; done
cat "$N" >> "$E"; echo "written: $(cut -d= -f1 "$N" | tr '\n' ' ')"; rm -f "$N"; chmod 600 "$E"
cd /opt/sinder/server-instance/deploy && docker compose -p sinder-server -f docker-compose.server.yml up -d --force-recreate 2>&1 | tail -2
sleep 30; printf "%-40s %s\n" "https://desk.216-158-234-218.sslip.io/login" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://desk.216-158-234-218.sslip.io/login)"
