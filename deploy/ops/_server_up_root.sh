#!/bin/sh
# Runs as root on the server (called by server-up.sh).
set -eu
. /opt/sinder/server-instance/deploy/ops/_server_compose.sh   # server_compose: test or production mode (deploy/CUTOVER.md)
D=/opt/sinder/server-instance; G=/opt/sinder/gateway/Caddyfile; HOST=desk.216-158-234-218.sslip.io
T=$(cat /opt/sinder/data_token)
red() { sed "s/$T/<token>/g"; }
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$@" || true; }
line() { printf "%-40s %s\n" "$1" "$2"; }

IP=$(curl -s -4 --max-time 10 ifconfig.me || true)
line "public IPv4 matches $HOST" "$([ "$(echo "$IP" | tr . -)" = 216-158-234-218 ] && echo yes || echo "NO ($IP)")"

echo "== 1. database backup (only if the newest is older than 6 hours)"
L=$(ls -1t /opt/sinder/backup/db/*.enc 2>/dev/null | head -1 || true)
AGE=$([ -n "$L" ] && echo $(( $(date +%s) - $(stat -c %Y "$L") )) || echo 999999)
if [ "$AGE" -gt 21600 ]; then bash /opt/sinder/repo/deploy/ops/_backup_root.sh 2>&1 | tail -6
else echo "newest backup $(basename "$L") is $((AGE / 60)) minutes old: no new backup"; fi

echo "== 1b. .env lines whose value is only a comment (docker compose reads the comment text as the value)"
E=/opt/sinder/repo/deploy/.env; RX='^[A-Za-z_][A-Za-z0-9_]*=[[:space:]]*#'
if grep -qE "$RX" $E; then
  cp -p $E "$E.bak-$(date -u +%Y%m%dT%H%M%SZ)"; chmod 600 $E.bak-*
  echo "blanked (were comment text, now empty): $(grep -oE "$RX" $E | cut -d= -f1 | tr '\n' ' ')"
  sed -E 's/^([A-Za-z_][A-Za-z0-9_]*)=[[:space:]]*#.*$/\1=/' $E > $E.tmp; cat $E.tmp > $E; rm -f $E.tmp; chmod 600 $E
else echo "none"; fi
echo "== 2. build (low priority) and start, mode $(server_mode)"
# the check-now worker (service checknow, production overlay) runs as uid 10001 and keeps its state here
mkdir -p /opt/sinder/checknow && chown 10001 /opt/sinder/checknow && chmod 700 /opt/sinder/checknow
cd $D/deploy
t0=$(date +%s)
nice -n 15 ionice -c 3 sh -c ". $D/deploy/ops/_server_compose.sh; server_compose build --pull" 2>&1 | grep -E "ERROR|error:|Built|exporting to image|naming to" | tail -5 || true
echo "build took $(( $(date +%s) - t0 ))s"
server_compose up -d --force-recreate 2>&1 | tail -3
for i in $(seq 1 24); do s=$(docker inspect -f '{{.State.Health.Status}}' sinder-server-app 2>/dev/null || echo none); [ "$s" = healthy ] && break; sleep 5; done
line "container sinder-server-app" "$s"

echo "== 3. HTTPS through the gateway Caddy (second site block)"
if ! grep -q "^$HOST {" $G; then
  cp -p $G "$G.bak-$(date -u +%Y%m%dT%H%M%SZ)"; chmod 600 $G.bak-*
  printf '\n%s {\n\treverse_proxy sinder-server-app:3000\n}\n' "$HOST" >> $G   # append in place: the bind mount keeps the same file
  echo "site block added for $HOST"
else echo "site block already present"; fi
if [ "$(server_mode)" = production ] && ! grep -q "^desk.sinder.pro {" $G; then   # production: keep the public name too
  printf '\n%s {\n\treverse_proxy sinder-server-app:3000\n}\n' desk.sinder.pro >> $G; echo "site block added for desk.sinder.pro (production mode)"; fi
if docker exec sinder-gateway caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  docker exec sinder-gateway caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile 2>&1 | red | grep -iE "error" | head -3 || true
  echo "gateway config valid, reloaded"
else
  B=$(ls -1t $G.bak-* | head -1); cat "$B" > $G; echo "GATEWAY CONFIG INVALID: restored the previous file, not reloaded"
fi
for i in $(seq 1 12); do c=$(code "https://$HOST/login"); [ "$c" = 200 ] && break; sleep 10; done

echo "== 4. checks"
line "https://$HOST/login" "$c   (want 200)"
line "signed-out /api/panel/winners" "$(code "https://$HOST/api/panel/winners")   (want 401)"
line "certificate issuer" "$(echo | openssl s_client -connect "$HOST:443" -servername "$HOST" 2>/dev/null | openssl x509 -noout -issuer 2>/dev/null | sed 's/.*O = //; s/,.*//')"
ex() { docker exec sinder-server-app node -e "fetch('$1').then(r=>console.log(r.status)).catch(e=>console.log('ERR '+e.message))" 2>&1 | tail -1; }
line "app reads data: suppliers index" "$(ex http://data:8080/data/web/suppliers.enc)   (want 200)"
line "app reads data: panel page" "$(ex http://data:8080/dealdesk/public/panel.html)   (want 200)"
line "live gateway data path still serves" "$(code "https://216-158-234-218.sslip.io/$T/deploy/README.md")   (want 200)"
line "live gateway outside the path" "$(code "https://216-158-234-218.sslip.io/deploy/README.md")   (want 404)"
echo "== 5. isolation from the live sheets (/api/staging-check: one marked row to the staging state sheet, one write to the live engine sheet that must be refused)"
curl -s --max-time 60 "https://$HOST/api/staging-check" | tr ',' '\n' | grep -E '"(env|sheets_configured|state_sheet|engine_sheet|state_is_engine|suppression_goes_to|mail_can_send|write_to_state|read_back_from_state|write_to_live_engine|ok)"' | cut -c1-160
echo "== safety switches inside the instance"
docker exec sinder-server-app sh -c 'for k in AGENT_MAIL_LIVE TELEGRAM_OFF DESK_ENV STATE_TABS_EXTRA; do echo "$k=$(printenv $k)"; done; for k in RESEND_API_KEY VAPID_PRIVATE_KEY; do [ -n "$(printenv $k)" ] && echo "$k: set (NOT SAFE)" || echo "$k: empty"; done'
line "cron service of sinder-server" "$(docker ps -a --format '{{.Names}}' | grep -c '^sinder-server-cron' || true) containers (want $([ "$(server_mode)" = production ] && echo 1 || echo 0), mode $(server_mode))"
echo "== 6. app log"
N=$(docker logs sinder-server-app 2>&1 | wc -l); E=$(docker logs sinder-server-app 2>&1 | grep -ciE "error|ECONNREFUSED|ENOTFOUND" || true)
line "log lines / error lines" "$N / $E"
docker logs sinder-server-app 2>&1 | grep -oiE "(error|ECONNREFUSED|ENOTFOUND)[^,;{}\"']{0,60}" | sort | uniq -c | sort -rn | head -5 | red
echo "== 7. containers"; docker ps --format '  {{.Names}}\t{{.Status}}'
