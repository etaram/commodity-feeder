#!/usr/bin/env bash
# Screen check of the server instance: every screen answers, none is empty, none shows stale data
# (deploy/ops/_screen_check.js). Read-only. Runs after every server-up / server-env / cutover-switch and on its own.
# Fails (exit 1) when a screen shows an error, comes back empty or is stale.
set -euo pipefail
if [ -z "${BASE:-}" ]; then
  if [ "$(cat /opt/sinder/server-mode 2>/dev/null || true)" = "production" ]; then BASE=https://desk.sinder.pro; else BASE=https://desk.216-158-234-218.sslip.io; fi
fi
echo "screen check of $BASE at $(date -u +%FT%TZ)"
for i in $(seq 1 30); do docker exec sinder-server-app node -e 'fetch("http://127.0.0.1:3000/login").then(r=>process.exit(r.status<500?0:1)).catch(()=>process.exit(1))' && break; sleep 5; done
docker exec -i -e BASE="$BASE" sinder-server-app node - < "$(dirname "$0")/_screen_check.js"
