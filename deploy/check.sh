#!/usr/bin/env bash
# Checks the stack from inside the server, before the domain points here. Prints one line per check.
cd "$(dirname "$0")"
ok() { printf "%-34s %s\n" "$1" "$2"; }
c() { docker compose exec -T app node -e "fetch('$1',{redirect:'manual'}).then(async r=>{console.log(r.status)}).catch(e=>console.log('ERR '+e.message))" 2>/dev/null; }
ok "app /login" "$(c http://127.0.0.1:3000/login)   (want 200)"
ok "app /api/panel/winners signed out" "$(c http://127.0.0.1:3000/api/panel/winners)   (want 401)"
ok "data service: supplier index" "$(c http://data:8080/data/web/suppliers.enc)   (want 200)"
ok "data service: panel page" "$(c http://data:8080/dealdesk/public/panel.html)   (want 200)"
ok "database" "$(docker compose exec -T db pg_isready -U sinder -d sinder 2>&1 | tail -1)"
ok "cron container" "$(docker compose ps --format '{{.State}}' cron)"
set -a; . ./.env; set +a
ok "scheduled route with CRON_SECRET" "$(docker compose exec -T app node -e "fetch('http://127.0.0.1:3000/api/cron/digest?dry=1',{headers:{authorization:'Bearer '+process.env.CRON_SECRET}}).then(r=>console.log(r.status)).catch(e=>console.log('ERR '+e.message))")   (want 200)"
for k in AUTH_SECRET WEB_INDEX_KEY GOOGLE_SERVICE_ACCOUNT_JSON ANTHROPIC_API_KEY sinder_desk_bot TELEGRAM_WEBHOOK_SECRET ZOHO_SMTP_PASS; do
  v=$(grep -E "^$k=" .env | cut -d= -f2-); ok "env $k" "$([ -n "$v" ] && echo set || echo MISSING)"
done
