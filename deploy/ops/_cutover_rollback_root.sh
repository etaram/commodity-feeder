#!/bin/sh
# Runs as root on the server (called by cutover-rollback.sh). Returns the server instance to the isolated test mode:
# mode file removed, cron service stopped, desk.sinder.pro site block removed, app recreated from the base compose file
# (staging sheet, mail off, bot off). Never touches Vercel or DNS. Safe to run more than once.
set -eu
. /opt/sinder/server-instance/deploy/ops/_server_compose.sh
G=/opt/sinder/gateway/Caddyfile; SSLIP=desk.216-158-234-218.sslip.io; TS=$(date -u +%Y%m%dT%H%M%SZ)
line() { printf "%-46s %s\n" "$1" "$2"; }
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$@" || true; }
echo "== DNS of $DESK_PUBLIC now: $(dns_answers https://cloudflare-dns.com/dns-query)"
echo "== 1. mode file removed, cron service stopped"
rm -f "$SERVER_MODE_FILE"
docker rm -f sinder-server-cron >/dev/null 2>&1 && echo "  sinder-server-cron removed" || echo "  no cron container"
echo "== 2. gateway: $DESK_PUBLIC site block removed (the $SSLIP block stays)"
if grep -q "^$DESK_PUBLIC {" $G; then
  cp -p $G "$G.bak-$TS"; chmod 600 "$G.bak-$TS"
  awk -v h="$DESK_PUBLIC {" '$0==h{skip=1;next} skip&&$0=="}"{skip=0;next} !skip' "$G.bak-$TS" > $G.tmp; cat $G.tmp > $G; rm -f $G.tmp
  if docker exec sinder-gateway caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
    docker exec sinder-gateway caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || true; echo "  removed, reloaded"
  else cat "$G.bak-$TS" > $G; echo "  GATEWAY CONFIG INVALID after removal: previous file restored"; fi
else echo "  no such block"; fi
echo "== 3. app back to test mode (base compose file only)"
server_compose up -d --force-recreate server-app 2>&1 | tail -3
for i in $(seq 1 24); do s=$(docker inspect -f '{{.State.Health.Status}}' sinder-server-app 2>/dev/null || echo none); [ "$s" = healthy ] && break; sleep 5; done
line "  container sinder-server-app" "$s"
docker exec sinder-server-app sh -c 'for k in DESK_ENV AGENT_MAIL_LIVE TELEGRAM_OFF; do printf "  %-44s %s\n" "inside: $k" "$(printenv $k)"; done'
echo "== 4. telegram webhook (the URL is https://$DESK_PUBLIC/api/telegram in both modes: with DNS back on Vercel it lands there)"
if tg_token_set; then tg_call info; else echo "  no bot token in the server .env"; fi
echo "== 5. isolation check"
line "  https://$SSLIP/login" "$(code "https://$SSLIP/login")"
curl -s --max-time 60 "https://$SSLIP/api/staging-check" | tr ',' '\n' | grep -E '"(state_sheet|state_is_engine|mail_can_send|write_to_live_engine|ok)"' | cut -c1-160 || true
echo "== done: mode $(server_mode)"
