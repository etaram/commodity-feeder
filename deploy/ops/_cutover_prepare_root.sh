#!/bin/sh
# Runs as root on the server (called by cutover-prepare.sh). READ-ONLY: changes no file, no container, no webhook.
# Lines starting with "K " are machine lines (key, state) that cutover-prepare.sh turns into the readiness table.
set -u
. /opt/sinder/server-instance/deploy/ops/_server_compose.sh
E=$SERVER_ENV_FILE; G=/opt/sinder/gateway/Caddyfile; SSLIP=desk.216-158-234-218.sslip.io
line() { printf "%-46s %s\n" "$1" "$2"; }
code() { curl -s -o /dev/null -w "%{http_code}" --max-time 20 "$@" || true; }
echo "== mode now: $(server_mode)   (.env $([ -f "$E" ] && echo "present, mode $(stat -c %a "$E")" || echo MISSING))"
for k in AUTH_SECRET GOOGLE_SERVICE_ACCOUNT_JSON ANTHROPIC_API_KEY WEB_INDEX_KEY ZOHO_SMTP_USER ZOHO_SMTP_PASS SEND_APPROVERS \
         ZOHO_SMTP_HOST ZOHO_FROM_ADDRESS MAIL_ABOUT NOTIFY_EMAIL RESEND_API_KEY TELEGRAM_BOT_TOKEN sinder_desk_bot \
         TELEGRAM_WEBHOOK_SECRET VAPID_PRIVATE_KEY VAPID_PUBLIC_KEY VAPID_SUBJECT CRON_SECRET TEAM_USER TEAM_PASSCODE \
         ANTHROPIC_WORKSPACE_ID DATA_BASE_URL AGENT_MAIL_LIVE TELEGRAM_OFF; do echo "K $k $(env_state "$k")"; done
echo "== DNS of $DESK_PUBLIC now (public resolvers)"
line "  cloudflare" "$(dns_answers https://cloudflare-dns.com/dns-query)"
line "  google" "$(dns_answers https://dns.google/resolve)"
line "  points at this server ($SERVER_IP)" "$(dns_points_here && echo yes || echo "no (expected before the switch)")"
caa=$(curl -s --max-time 10 -H 'accept: application/dns-json' "https://cloudflare-dns.com/dns-query?name=sinder.pro&type=CAA" | grep -oE '"data":"[^"]*"' | cut -d'"' -f4 | tr '\n' ' ')
line "  CAA of sinder.pro" "${caa:-none (any CA may issue: Let's Encrypt OK)}"
echo "== gateway (Caddy)"
line "  site block $SSLIP" "$(grep -q "^$SSLIP {" $G && echo present || echo MISSING)"
line "  site block $DESK_PUBLIC" "$(grep -q "^$DESK_PUBLIC {" $G && echo "present (unexpected before the switch)" || echo "absent (added by cutover-switch)")"
echo "== instance"
line "  container sinder-server-app" "$(docker inspect -f '{{.State.Health.Status}}' sinder-server-app 2>/dev/null || echo none)"
line "  https://$SSLIP/login" "$(code "https://$SSLIP/login")"
docker exec sinder-server-app sh -c 'for k in DESK_ENV AGENT_MAIL_LIVE TELEGRAM_OFF DATA_BASE_URL; do printf "  %-44s %s\n" "inside: $k" "$(printenv $k)"; done' 2>/dev/null || true
line "  inside: app reads the data service" "$(docker exec sinder-server-app node -e "fetch('http://data:8080/data/web/suppliers.enc').then(r=>console.log(r.status)).catch(e=>console.log('ERR'))" 2>&1 | tail -1)   (want 200)"
line "  cron containers running (any project)" "$(docker ps --format '{{.Names}}' | grep -iE 'cron' | tr '\n' ' ' || true)"
line "  docker compose version" "$(docker compose version --short 2>/dev/null || echo unknown)"
line "  production overlay parses" "$(server_compose_prod config -q >/dev/null 2>&1 && echo yes || echo "NO: $(server_compose_prod config -q 2>&1 | tail -1 | cut -c1-100)")"
echo "== telegram (read-only getWebhookInfo from inside the instance)"
if tg_token_set; then tg_call info; else echo "  no bot token in the server .env yet"; fi
