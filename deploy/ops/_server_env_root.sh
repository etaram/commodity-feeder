#!/bin/sh
# Runs as root on the server (called by server-env.sh). Reads KEY=VALUE lines on stdin and writes them into the .env.
set -eu
E=/opt/sinder/repo/deploy/.env; umask 077
cp -p "$E" "$E.bak-$(date -u +%Y%m%dT%H%M%SZ)"; chmod 600 "$E".bak-*
N=$(mktemp); cat > "$N"
cut -d= -f1 "$N" | while read -r k; do grep -vE "^$k=" "$E" > "$E.tmp" || true; cat "$E.tmp" > "$E"; rm -f "$E.tmp"; done
cat "$N" >> "$E"; echo "written: $(cut -d= -f1 "$N" | tr '\n' ' ')"; rm -f "$N"; chmod 600 "$E"
# The server instance signs its own sessions: a fresh random AUTH_SECRET when none is set (never copied from Vercel,
# never printed). Sessions of the two instances are therefore separate, which is what we want until the domain moves.
if ! grep -qE '^AUTH_SECRET=.{32,}' "$E"; then grep -v '^AUTH_SECRET=' "$E" > "$E.tmp" || true; cat "$E.tmp" > "$E"; rm -f "$E.tmp"
  printf 'AUTH_SECRET=%s\n' "$(head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | cut -c1-48)" >> "$E"; chmod 600 "$E"; echo "AUTH_SECRET generated on the server"; fi
. /opt/sinder/server-instance/deploy/ops/_server_compose.sh
echo "mode: $(server_mode)"; server_compose up -d --force-recreate server-app 2>&1 | tail -2
if [ "$(server_mode)" = production ]; then
  sleep 30; printf "%-40s %s\n" "https://desk.sinder.pro/login" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://desk.sinder.pro/login)"
  echo "production mode: no isolation check (/api/staging-check answers 404)"; exit 0; fi
sleep 30; printf "%-40s %s\n" "https://desk.216-158-234-218.sslip.io/login" "$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 https://desk.216-158-234-218.sslip.io/login)"
echo "isolation check (/api/staging-check):"
curl -s --max-time 60 https://desk.216-158-234-218.sslip.io/api/staging-check | tr ',' '\n' | grep -E '"(state_sheet|state_is_engine|mail_can_send|write_to_state|read_back_from_state|write_to_live_engine|ok)"' | cut -c1-160
