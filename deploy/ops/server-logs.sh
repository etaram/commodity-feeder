#!/usr/bin/env bash
# Errors and warnings of the server instance app in the last 3 hours, de-duplicated, e-mail addresses and long
# tokens masked (logs of this workflow are public). Read-only.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c 'docker logs --since 3h sinder-server-app 2>&1' \
 | grep -iE "error|fail|warn|refused|denied|unauthor|not set|missing|timeout|exception|cannot|could not" \
 | grep -v "DEP0169\|trace-deprecation" \
 | sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/<email>/g; s/[A-Za-z0-9_-]{32,}/<long>/g; s/[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+Z//g' \
 | cut -c1-220 | sort | uniq -c | sort -rn | head -60
echo "== requests with status 4xx/5xx (path and status only)"
asroot sh -c 'docker logs --since 3h sinder-gateway 2>&1' | grep -o '"uri":"[^"]*","[^}]*"status":[45][0-9][0-9]' 2>/dev/null | sed -E 's/"uri":"([^"?]*)[^"]*".*"status":([0-9]+)/\2 \1/' | sort | uniq -c | sort -rn | head -40 || true
echo "== live Sheets reads from inside the instance (status, ms, row counts only)"
docker exec -i -w /app sinder-server-app node - < "$(dirname "$0")/_sheets_probe.js" 2>&1 | head -40 || true
echo "== signed-out requests inside the instance (want 401; status only)"
docker exec -i sinder-server-app node - <<'JS' 2>&1 | head -40 || true
const B = "http://127.0.0.1:3000";
const gets = ["/api/panel/today", "/api/panel/brief", "/api/me", "/api/profile", "/api/projects", "/api/activity", "/api/panel/server"];
const keys = ["pursuits", "ptasks", "projects", "jobs", "intel", "contacts", "bd", "approvals", "accounts", "tenders", "stats"];
(async () => {
  for (const p of gets) { try { const r = await fetch(B + p, { redirect: "manual" }); console.log(`  GET  ${p.padEnd(22)} ${r.status}`); } catch (e) { console.log(`  GET  ${p} ERR`); } }
  for (const k of keys) { try { const r = await fetch(B + "/api/panel/get", { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ key: k }), redirect: "manual" }); console.log(`  POST /api/panel/get ${k.padEnd(10)} ${r.status}`); } catch (e) { console.log(`  POST get ${k} ERR`); } }
})();
JS
echo "== Next cache directory writable by the app user"
docker exec sinder-server-app sh -c 'id -un; touch /app/.next/cache/.w 2>/dev/null && echo writable && rm -f /app/.next/cache/.w || echo NOT writable'
