#!/bin/sh
# Runs as root on the server (called by cutover-switch.sh). Puts the server instance into PRODUCTION mode for
# desk.sinder.pro. Refuses unless public DNS already points desk.sinder.pro at this server. Never touches Vercel or DNS.
set -eu
. /opt/sinder/server-instance/deploy/ops/_server_compose.sh
E=$SERVER_ENV_FILE; G=/opt/sinder/gateway/Caddyfile; SSLIP=desk.216-158-234-218.sslip.io; TS=$(date -u +%Y%m%dT%H%M%SZ)
line() { printf "%-46s %s\n" "$1" "$2"; }
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$@" || true; }
setkv() { grep -vE "^$1=" "$E" > "$E.tmp" || true; [ -z "${2+x}" ] || printf '%s=%s\n' "$1" "$2" >> "$E.tmp"; cat "$E.tmp" > "$E"; rm -f "$E.tmp"; chmod 600 "$E"; }
delkv() { grep -vE "^$1=" "$E" > "$E.tmp" || true; cat "$E.tmp" > "$E"; rm -f "$E.tmp"; chmod 600 "$E"; }

echo "== 1. DNS gate"
line "  cloudflare" "$(dns_answers https://cloudflare-dns.com/dns-query)"
line "  google" "$(dns_answers https://dns.google/resolve)"
line "  this server's IPv4" "$(curl -s -4 --max-time 10 ifconfig.me || echo unknown)"
if ! dns_points_here; then echo "REFUSED: $DESK_PUBLIC does not resolve (only) to $SERVER_IP yet. Nothing was changed."; exit 1; fi
echo "  ok: $DESK_PUBLIC resolves to this server"

echo "== 2. required keys"
miss=""; for k in GOOGLE_SERVICE_ACCOUNT_JSON ANTHROPIC_API_KEY WEB_INDEX_KEY AUTH_SECRET; do env_has $k || miss="$miss $k"; done
if [ -n "$miss" ]; then echo "REFUSED: missing in the server .env:$miss (add SERVER_<KEY> secrets, run server-env). Nothing was changed."; exit 1; fi
echo "  ok"

echo "== 3. .env switches (backup .env.bak-$TS)"
cp -p "$E" "$E.bak-$TS"; chmod 600 "$E.bak-$TS"
env_has CRON_SECRET || { setkv CRON_SECRET "$(head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | cut -c1-48)"; echo "  CRON_SECRET generated on the server"; }
if env_has ZOHO_SMTP_USER && env_has ZOHO_SMTP_PASS && env_has SEND_APPROVERS; then delkv AGENT_MAIL_LIVE; echo "  mail: ON (AGENT_MAIL_LIVE removed)"
else setkv AGENT_MAIL_LIVE 0; echo "  mail: stays OFF (AGENT_MAIL_LIVE=0): ZOHO_SMTP_USER, ZOHO_SMTP_PASS and SEND_APPROVERS are not all set"; fi
# the webhook secret is ours to choose: setWebhook (step 6) registers it with Telegram, so a new one replaces Vercel's
tg_token_set && ! env_has TELEGRAM_WEBHOOK_SECRET && { setkv TELEGRAM_WEBHOOK_SECRET "$(head -c 64 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | cut -c1-48)"; echo "  TELEGRAM_WEBHOOK_SECRET generated on the server (registered with Telegram in step 6)"; }
if tg_token_set && env_has TELEGRAM_WEBHOOK_SECRET; then delkv TELEGRAM_OFF; TG=on; echo "  telegram: ON (TELEGRAM_OFF removed)"
else setkv TELEGRAM_OFF 1; TG=off; echo "  telegram: stays OFF (token or TELEGRAM_WEBHOOK_SECRET missing); the webhook is not touched"; fi
line "  web push" "$(env_has VAPID_PRIVATE_KEY && echo on || echo "off (VAPID_PRIVATE_KEY missing)")"
line "  digest / alert mail (Resend)" "$(env_has RESEND_API_KEY && echo on || echo "off (RESEND_API_KEY missing)")"

echo "== 4. production mode: app recreated with the live sheet, cron service started"
server_compose_prod config -q || { cp -p "$E.bak-$TS" "$E"; echo "REFUSED: production compose files do not parse; .env restored, mode unchanged."; exit 1; }
echo production > "$SERVER_MODE_FILE"; chmod 644 "$SERVER_MODE_FILE"
server_compose up -d --force-recreate server-app server-cron 2>&1 | tail -3
for i in $(seq 1 24); do s=$(docker inspect -f '{{.State.Health.Status}}' sinder-server-app 2>/dev/null || echo none); [ "$s" = healthy ] && break; sleep 5; done
line "  container sinder-server-app" "$s"
line "  container sinder-server-cron" "$(docker inspect -f '{{.State.Status}}' sinder-server-cron 2>/dev/null || echo none)"

echo "== 5. gateway site block for $DESK_PUBLIC (the $SSLIP block stays)"
if ! grep -q "^$DESK_PUBLIC {" $G; then
  cp -p $G "$G.bak-$TS"; chmod 600 "$G.bak-$TS"
  printf '\n%s {\n\treverse_proxy sinder-server-app:3000\n}\n' "$DESK_PUBLIC" >> $G
  echo "  site block added"
else echo "  site block already present"; fi
if docker exec sinder-gateway caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1; then
  docker exec sinder-gateway caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 || true; echo "  gateway config valid, reloaded"
else [ -f "$G.bak-$TS" ] && cat "$G.bak-$TS" > $G; echo "  GATEWAY CONFIG INVALID: previous file restored, not reloaded. Run cutover-rollback."; fi
for i in $(seq 1 18); do c=$(code "https://$DESK_PUBLIC/login"); [ "$c" = 200 ] && break; sleep 10; done

echo "== 6. telegram webhook (same URL https://$DESK_PUBLIC/api/telegram, same secret; DNS decides where it lands)"
if [ "$TG" = on ]; then tg_call set "https://$DESK_PUBLIC/api/telegram"; else echo "  skipped (bot off)"; fi

echo "== 7. verification"
line "  https://$DESK_PUBLIC/login" "$c   (want 200, certificate verified by curl)"
line "  certificate issuer / verify" "$(echo | openssl s_client -connect "$DESK_PUBLIC:443" -servername "$DESK_PUBLIC" 2>/dev/null | openssl x509 -noout -issuer 2>/dev/null | sed 's/.*O = //; s/,.*//') / $(curl -s -o /dev/null -w '%{ssl_verify_result}' --max-time 20 "https://$DESK_PUBLIC/login" || echo ?) (0 = valid)"
line "  https://$DESK_PUBLIC/api/staging-check" "$(code "https://$DESK_PUBLIC/api/staging-check")   (want 404: production)"
line "  https://$SSLIP/login" "$(code "https://$SSLIP/login")   (want 200)"
line "  signed-out /api/panel/winners" "$(code "https://$DESK_PUBLIC/api/panel/winners")   (want 401)"
docker exec sinder-server-app sh -c 'for k in DESK_ENV AGENT_MAIL_LIVE TELEGRAM_OFF SHEETS_READONLY_IDS STATE_TABS_EXTRA; do printf "  %-44s %s\n" "inside: $k" "$(printenv $k)"; done
  s=$(printenv STATE_SHEET_ID); printf "  %-44s %s\n" "inside: STATE_SHEET_ID" "...${s#${s%??????}}"
  for k in RESEND_API_KEY VAPID_PRIVATE_KEY CRON_SECRET; do [ -n "$(printenv $k)" ] && v=set || v=empty; printf "  %-44s %s\n" "inside: $k" "$v"; done'
if [ "$TG" = on ]; then tg_call info; fi
echo "== done: mode $(server_mode). Now do the Vercel steps of deploy/CUTOVER.md in the same minute."
