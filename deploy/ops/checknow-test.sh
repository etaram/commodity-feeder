#!/usr/bin/env bash
# End-to-end proof of "check the website" on the live server: ONE request for a well-known company (Siemens Energy,
# DEU) through the app's own route (POST /api/panel/company-check with the app's self-check key, derived from
# AUTH_SECRET inside the container as lib/selfkey.ts does; never printed), then GET every 5 s until a check newer than
# the request appears. Prints the timings and the verdict only.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
echo "== worker"; docker inspect -f '{{.State.Status}} since {{.State.StartedAt}}' sinder-server-checknow 2>&1 | tail -1
docker exec -i sinder-server-app node - <<'JS'
const crypto = require("node:crypto");
const key = crypto.createHmac("sha256", process.env.AUTH_SECRET || "").update("dd-selfcheck-v1").digest("hex");
const B = "http://127.0.0.1:3000/api/panel/company-check", H = { "content-type": "application/json", "x-dd-audit": key };
const name = "Siemens Energy", country = "DEU";
(async () => {
  const t0 = Date.now();
  const p = await fetch(B, { method: "POST", headers: H, body: JSON.stringify({ name, country, website: "https://www.siemens-energy.com" }) }).then((r) => r.json());
  console.log(`POST ${p.ok ? "ok" : "FAILED"}  requested_at ${p.requested_at}  eta_s ${p.eta_s}  note: ${p.note || p.error}`);
  if (!p.ok) process.exit(1);
  for (;;) {
    await new Promise((r) => setTimeout(r, 5000));
    const s = ((Date.now() - t0) / 1000).toFixed(0);
    const j = await fetch(`${B}?name=${encodeURIComponent(name)}&country=${country}`, { headers: H }).then((r) => r.json()).catch((e) => ({ ok: false, error: String(e) }));
    const c = j.check || {};
    if (c.checked_at && Date.parse(c.checked_at) >= Date.parse(p.requested_at) - 5000) {
      console.log(`RESULT after ${s}s: checked_at ${c.checked_at}  verdict ${c.verdict}  name_match ${c.name_match}  domain ${c.domain}  reason ${c.reason}`);
      console.log(`  products: ${String(c.products || "").slice(0, 120)}`);
      console.log(`  e-mails on its domain: ${c.emails ? String(c.emails).split(";").length : 0}   phones: ${c.phones ? String(c.phones).split(";").length : 0}   gaps: ${c.gaps || "-"}`);
      return;
    }
    if (Date.now() - t0 > 180000) { console.log(`NO RESULT after ${s}s (latest row: ${c.checked || "none"} ${c.checked_at || ""})`); process.exit(1); }
  }
})().catch((e) => { console.log("ERR " + String(e.message || e).slice(0, 120)); process.exit(1); });
JS
echo "== worker log (last lines, e-mails masked)"
docker logs --tail 6 sinder-server-checknow 2>&1 | sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/<email>/g' | cut -c1-200
