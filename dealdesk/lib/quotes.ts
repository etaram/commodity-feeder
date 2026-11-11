// Quote comparison and the deal funnel.
//
// compareQuotes: the quotes saved on one deal, put on one basis (USD per tonne, or per unit when the unit is not a
// mass), grouped by Incoterm and place (a CFR Mombasa price is not comparable with an FOB Santos one), ranked within
// each group, with gaps listed (no price, unconfirmed availability, expired validity) and the distance to the owner's
// target price when one is given. Nothing is converted silently: every converted row says from what.
//
// funnel: counts of what the deal team has done, from the agent's own records: runs, messages proposed, approved and
// sent, rejected, waiting; quotes received. It answers "is the machine producing, and where does it stall".
import { getRange } from "@/lib/panel";
import { readDeal } from "@/lib/deal";
import { ENGINE_SHEET, readRanges } from "@/lib/sheets";

const RUNS = "Agent Runs", APPROVALS = "Agent Approvals";   // the deal agent's tabs (lib/dealagent.ts)

const TONNE: Record<string, number> = { t: 1, mt: 1, ton: 1, tonne: 1, tons: 1, tonnes: 1, kg: 0.001, kgs: 0.001, lb: 0.000453592, lbs: 0.000453592, quintal: 0.1, qq: 0.046 };

async function fx(): Promise<Map<string, number>> {
  const g = await getRange("fx").catch(() => [] as string[][]);
  const h = g[0] || [];
  const ic = h.indexOf("currency"), iv = h.indexOf("usd_per_unit");
  const m = new Map<string, number>([["USD", 1]]);
  for (const r of g.slice(1)) { const v = parseFloat(String(r[iv])); if (r[ic] && v > 0) m.set(String(r[ic]).toUpperCase(), v); }
  return m;
}

export type Compared = { supplier: string; country: string; product: string; incoterm: string; place: string; price: number | null; unit: string; currency: string;
  usd: number | null; basis: string; vs_target_pct: number | null; lead_time_days: number | null; payment: string; valid_until: string; flags: string[]; rank: number };

export async function compareQuotes(dealId: string, ws: string, target?: { usd: number; unit: string }) {
  const { records } = await readDeal(dealId, ws);
  const last = new Map<string, Record<string, unknown>>();
  for (const r of records.filter((x) => x.kind === "quote")) last.set(r.record_id, r.data);   // latest version per quote
  const rates = await fx();
  const today = new Date().toISOString().slice(0, 10);
  const rows: Compared[] = [];
  for (const q of last.values()) {
    const unit = String(q.unit || "").toLowerCase().replace(/[^a-z]/g, "");
    const price = typeof q.unit_price === "number" ? q.unit_price : null;
    const cur = String(q.currency || "").toUpperCase();
    const flags: string[] = [];
    let usd: number | null = null, basis = "";
    if (price == null) flags.push("no price");
    else if (!rates.has(cur)) flags.push(`no rate for ${cur || "missing currency"}`);
    else {
      const perUnitUsd = price * rates.get(cur)!;
      if (TONNE[unit]) { usd = perUnitUsd / TONNE[unit]; basis = `USD/t${cur !== "USD" || unit !== "t" ? ` (from ${price} ${cur}/${q.unit})` : ""}`; }
      else { usd = perUnitUsd; basis = `USD/${q.unit || "unit"}${cur !== "USD" ? ` (from ${price} ${cur})` : ""}`; }
    }
    if (q.availability !== "confirmed") flags.push("availability unconfirmed");
    if (q.valid_until && String(q.valid_until) < today) flags.push("validity expired");
    if (!q.incoterm) flags.push("no Incoterm");
    let vs: number | null = null;
    if (target && usd != null && basis.startsWith(`USD/${target.unit}`)) vs = Math.round((usd / target.usd - 1) * 1000) / 10;
    rows.push({ supplier: String(q.supplier || ""), country: String(q.country || ""), product: String(q.product || ""), incoterm: String(q.incoterm || ""), place: String(q.named_place || ""),
      price, unit: String(q.unit || ""), currency: cur, usd: usd == null ? null : Math.round(usd * 100) / 100, basis, vs_target_pct: vs,
      lead_time_days: typeof q.lead_time_days === "number" ? q.lead_time_days : null, payment: String(q.payment_terms || ""), valid_until: String(q.valid_until || ""), flags, rank: 0 });
  }
  const groups = new Map<string, Compared[]>();
  for (const r of rows) { const k = `${r.incoterm || "?"} ${r.place.toLowerCase()}`.trim(); groups.set(k, [...(groups.get(k) || []), r]); }
  for (const g of groups.values()) {
    g.sort((a, b) => (a.usd ?? Infinity) - (b.usd ?? Infinity) || a.flags.length - b.flags.length);
    g.forEach((r, i) => { r.rank = r.usd == null ? 0 : i + 1; });
  }
  return {
    deal_id: dealId, quotes: rows.length,
    groups: [...groups.entries()].map(([k, g]) => ({ basis: k, rows: g })),
    note: "Ranked only within the same Incoterm and place; a lower price with open flags is not yet the better offer.",
  };
}

export async function funnel(days = 30) {
  const since = new Date(Date.now() - days * 86400_000).toISOString();
  const [runsG, apprG] = (await readRanges(ENGINE_SHEET, [`'${RUNS}'!A2:E5000`, `'${APPROVALS}'!A2:E5000`]).catch(() => null)) || [[], []];
  const runStatus = new Map<string, string>();
  for (const r of runsG || []) if (r?.[0] && String(r[1]) >= since) runStatus.set(r[0], String(r[4]));
  const appr = new Map<string, string>();
  for (const r of apprG || []) if (r?.[0] && String(r[3]) >= since) appr.set(r[0], String(r[4]));   // last status per message
  const count = (m: Map<string, string>, ...v: string[]) => [...m.values()].filter((x) => v.includes(x)).length;
  return {
    days,
    runs: runStatus.size, runs_waiting_on_owner: count(runStatus, "waiting"), runs_done: count(runStatus, "done"),
    messages_proposed: appr.size, messages_sent: count(appr, "sent"), messages_rejected: count(appr, "rejected"),
    messages_waiting_approval: count(appr, "pending", "needs_review"), messages_failed: count(appr, "send_failed"),
  };
}
