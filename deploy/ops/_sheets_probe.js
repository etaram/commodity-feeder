// Piped into the server instance container by server-logs.sh (docker exec -i -w /app sinder-server-app node -).
// Times the panel's live Sheets reads (lib/panel.ts LIVE) one by one and all at once, and lists the STATE_TABS_EXTRA
// tabs that the state sheet lacks. Prints key, HTTP status, milliseconds and sizes only: no cell values, no secrets.
const { JWT } = require("google-auth-library");
const dns = require("node:dns").promises;
const API = "https://sheets.googleapis.com/v4/spreadsheets";
const LE = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y", SU = "1crzrRr4qrgt1WpAwNmCNPL4TfIrZUuTyqRGonVvwhuA";
const LIVE = { bd: [LE, "'BD Agent'!A1:M600"], accounts: [LE, "'Key Accounts'!A1:S400"], intel: [LE, "'Intel'!A1:P2000"],
  pursuits: [LE, "'Pursuits'!A1:V600"], jobs: [LE, "'Panel Jobs'!A1:L800"], contacts: [LE, "'Contacts'!A1:S1500"],
  projects: [LE, "'Projects'!A1:V300"], ptasks: [LE, "'Project Tasks'!A1:L3000"], approvals: [LE, "'Approvals'!A1:M2000"], stats: [SU, "'Stats'!A1:B60"] };
(async () => {
  const raw = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!raw) { console.log("probe: no service account in the container"); return; }
  try { const a = await dns.lookup("sheets.googleapis.com", { all: true }); console.log("dns sheets.googleapis.com:", a.map((x) => "v" + x.family).join(",")); } catch (e) { console.log("dns error:", e.code); }
  const k = JSON.parse(raw);
  const jwt = new JWT({ email: k.client_email, key: k.private_key, scopes: ["https://www.googleapis.com/auth/spreadsheets"] });
  let t = Date.now(); const { token } = await jwt.getAccessToken(); console.log(`token ${Date.now() - t} ms`);
  const get = async (sid, range) => {
    const t0 = Date.now();
    try {
      const r = await fetch(`${API}/${sid}/values:batchGet?ranges=${encodeURIComponent(range)}&valueRenderOption=FORMATTED_VALUE`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(30000) });
      const b = await r.text();
      let rows = 0; try { rows = (JSON.parse(b).valueRanges?.[0]?.values || []).length; } catch {}
      return `${r.status} ${Date.now() - t0} ms ${rows} rows${r.ok ? "" : " " + ((b.match(/"message":\s*"([^"]{0,60})/) || [])[1] || "")}`;
    } catch (e) { return `ERR ${Date.now() - t0} ms ${String(e.name || e).slice(0, 40)}`; }
  };
  console.log("-- one by one");
  for (const [key, [sid, range]] of Object.entries(LIVE)) console.log(`  ${key.padEnd(10)} ${await get(sid, range)}`);
  console.log("-- all at once (like a cold page load)");
  t = Date.now();
  const res = await Promise.all(Object.entries(LIVE).map(async ([key, [sid, range]]) => `  ${key.padEnd(10)} ${await get(sid, range)}`));
  console.log(res.join("\n")); console.log(`  total ${Date.now() - t} ms`);
  const st = (process.env.STATE_SHEET_ID || "").trim();
  if (st) {
    const r = await fetch(`${API}/${st}?fields=sheets.properties.title`, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(20000) });
    const have = new Set(((await r.json()).sheets || []).map((s) => s.properties.title));
    const extra = (process.env.STATE_TABS_EXTRA || "").split(",").map((x) => x.trim()).filter(Boolean);
    console.log(`state sheet: ${have.size} tabs; STATE_TABS_EXTRA missing there: ${extra.filter((x) => !have.has(x)).join(", ") || "none"}`);
  }
})().catch((e) => console.log("probe error:", String(e.name || e).slice(0, 60)));
