#!/usr/bin/env bash
# Starts the private data layer only: PostgreSQL, the data file service and its sync job. The web app, the proxy
# and the cron service stay off (the live site is still on Vercel). Prints no secrets.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c 'cd /opt/sinder/repo && git pull -q && cd deploy && docker compose up -d db data sync 2>&1 | tail -8'
sleep 20
docker ps --format '{{.Names}}\t{{.Status}}\t{{.Ports}}'
echo "== database answers"; asroot sh -c 'cd /opt/sinder/repo/deploy && docker compose exec -T db sh -c "pg_isready -U \$POSTGRES_USER && psql -U \$POSTGRES_USER -d \$POSTGRES_DB -Atc \"select version()\"" 2>&1 | tail -2'
echo "== ports open to the internet (expect 22 only, plus 80/443 when the proxy runs)"; asroot ss -ltnH | awk '{print $4}' | grep -vE "^127\.|^\[::1\]" | sort -u
echo "== data service"; asroot sh -c 'cd /opt/sinder/repo/deploy && docker compose exec -T data wget -qO- http://127.0.0.1:8080/deploy/README.md 2>&1 | head -c 120; echo; docker compose logs --tail 5 sync 2>&1 | tail -5'
