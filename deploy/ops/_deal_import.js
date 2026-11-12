// Runs inside the app container (deploy/ops/deal-import.sh). Reads one dossier from stdin:
//   { deal_id, owner_email, owner_name, records: [{ kind, record_id, data }] }
// and saves every record that is not on the deal yet through the app's own route (POST /api/deal), as the owner's
// session. A record already on the deal is left as it is (re-running loads nothing twice). Then reads the deal back
// (GET /api/deal) and the board (GET /api/deal?pipeline=1). Prints ids, kinds, statuses and counts only: the workflow
// log is public, so no content, no address and not the deal id itself.
const crypto = require("node:crypto");
const B = "http://127.0.0.1:3000/api/deal";
const tag = (s) => crypto.createHash("sha256").update(String(s)).digest("hex").slice(0, 8);
function session(email, name) {
  // the same token lib/auth.ts signSession issues: base64url("email|exp|role|name|ws") + "." + HMAC-SHA256(AUTH_SECRET)
  const sec = process.env.AUTH_SECRET || "";
  if (sec.length < 16) throw new Error("the container has no AUTH_SECRET");
  const body = `${email}|${Date.now() + 10 * 60e3}|admin|${String(name || "").replace(/[|\r\n]/g, " ").slice(0, 80)}|sinder`;
  return Buffer.from(body).toString("base64url") + "." + crypto.createHmac("sha256", sec).update(body).digest("base64url");
}
let raw = "";
process.stdin.on("data", (c) => (raw += c));
process.stdin.on("end", async () => {
  try {
    const p = JSON.parse(raw);
    if (!p.deal_id || !p.owner_email || !Array.isArray(p.records)) throw new Error("dossier needs deal_id, owner_email and records");
    const H = { "content-type": "application/json", cookie: `dd_session=${session(p.owner_email, p.owner_name)}` };
    const get = async (q) => { const r = await fetch(`${B}?${q}`, { headers: H }); const j = await r.json().catch(() => ({})); if (!r.ok || j.ok === false) throw new Error(`GET ${r.status} ${j.code || ""} ${String(j.error || "").slice(0, 80)}`); return j; };
    console.log(`deal #${tag(p.deal_id)}: ${p.records.length} records in the dossier`);
    const have = new Set(((await get(`id=${encodeURIComponent(p.deal_id)}`)).records || []).map((r) => `${r.kind}|${r.record_id}`));
    console.log(`already on the deal: ${have.size}`);
    let saved = 0, skipped = 0, failed = 0;
    for (const r of p.records) {
      if (have.has(`${r.kind}|${r.record_id}`)) { skipped++; continue; }
      const res = await fetch(B, { method: "POST", headers: H, body: JSON.stringify({ deal_id: p.deal_id, kind: r.kind, record_id: r.record_id, data: r.data }) });
      const j = await res.json().catch(() => ({}));
      if (res.ok && j.ok) { saved++; console.log(`saved   ${r.kind.padEnd(11)} ${r.record_id} v${j.version}`); }
      else { failed++; console.log(`FAILED  ${r.kind.padEnd(11)} ${r.record_id}: ${res.status} ${String(j.error || "").slice(0, 100)}`); }
    }
    console.log(`saved ${saved}, already there ${skipped}, failed ${failed}`);
    // read back what the panel will show
    const d = await get(`id=${encodeURIComponent(p.deal_id)}`);
    const by = {}, st = {};
    for (const r of d.records || []) { by[r.kind] = (by[r.kind] || 0) + 1; if (r.kind === "requirement" || r.kind === "party" || r.kind === "draft") st[`${r.kind}:${r.status}`] = (st[`${r.kind}:${r.status}`] || 0) + 1; }
    const owners = [...new Set((d.records || []).map((r) => (r.by === p.owner_email ? "owner" : "other")))];
    console.log(`read back: ${JSON.stringify(by)}  versions ${d.versions}`);
    console.log(`statuses: ${JSON.stringify(st)}`);
    console.log(`written by: ${owners.join(", ")}`);
    const stage = (d.records || []).find((r) => r.kind === "stage");
    console.log(`stage: ${stage ? stage.data.stage : "none"}  status: ${stage ? stage.data.status_label : "-"}  next actions ${stage ? (stage.data.actions || []).length : 0}  sources ${stage ? (stage.data.sources || []).length : 0}`);
    if (d.readiness) console.log(`readiness: reached ${d.readiness.reached || "none"}, next ${d.readiness.next}, missing ${d.readiness.missing.length}`);
    const pl = await get("pipeline=1");
    const row = (pl.deals || []).find((x) => x.deal_id === p.deal_id);
    console.log(`Deals in progress board: ${pl.deals.length} deals, this one ${row ? `listed (stage ${row.stage.stage}, suppliers ${row.parties.supplier || 0})` : "NOT LISTED"}`);
    if (failed || !row) process.exit(1);
  } catch (e) { console.log("ERROR " + String(e.message || e).slice(0, 160)); process.exit(1); }
});
