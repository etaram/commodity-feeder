import { intlPhone } from "@/lib/phone";
import { appendRow, ENGINE_SHEET, readRanges } from "./sheets";

// Private deal records (hidden tab 'Deal Records' in the engine sheet): quotes, requirements and economics for one
// deal, keyed by the opportunity id (a tender id, so a deal reuses the opportunity's identity).
// Append-only journal: every save is a new version of a record; the latest version wins; nothing is overwritten,
// so any change can be traced and undone by saving the earlier version again.
// Columns: A time, B deal_id, C kind, D record_id, E version, F status, G data_json, H by, I source, J note.
export type Kind = "quote" | "requirement" | "economics" | "party" | "stage";
export type DealRecord = { time: string; deal_id: string; kind: Kind; record_id: string; version: number; status: string; data: Record<string, unknown>; by: string; source: string };
const TAB = "Deal Records";

const INCOTERMS = new Set(["EXW", "FCA", "FAS", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"]);
const REQ_STATUS = new Set(["met", "not_met", "unknown", "missing"]);
const str = (v: unknown, n = 300) => String(v ?? "").replace(/[\r\t]+/g, " ").trim().slice(0, n);
const numOrNull = (v: unknown) => { if (v === "" || v == null) return null; const n = Number(v); return Number.isFinite(n) ? n : NaN; };
const isDate = (v: string) => /^\d{4}-\d{2}-\d{2}$/.test(v);

// Validates and cleans one record's data; returns an error message or the clean data. Unknown stays empty, never zero.
// The deal's process: one stage record (where it stands, the next step and its date, the owner) and the parties
// around it (supplier, financing, logistics, buyer, partner), each with its contact route and where the talk stands.
export const STAGES = ["lead", "qualified", "sourcing", "financing", "logistics", "offer", "negotiation", "won", "lost"] as const;
const ROLES = new Set(["supplier", "finance", "logistics", "buyer", "partner"]);
const PARTY_STATUS = new Set(["candidate", "contacted", "replied", "quoted", "selected", "dropped"]);
function cleanProcess(kind: "party" | "stage", d: Record<string, unknown>) {
  if (kind === "stage") {
    const st = str(d.stage, 20);
    const x = { stage: (STAGES as readonly string[]).includes(st) ? st : "lead", next_step: str(d.next_step, 240), next_date: isDate(str(d.next_date, 10)) ? str(d.next_date, 10) : "",
      owner: str(d.owner, 120), title: str(d.title, 240), country: str(d.country, 3).toUpperCase(), sector: str(d.sector, 80), value_usd: numOrNull(d.value_usd), deadline: str(d.deadline, 10), note: str(d.note, 600) };
    if (Number.isNaN(x.value_usd)) x.value_usd = null;
    return { ok: true as const, data: x, status: x.stage };
  }
  const role = str(d.role, 20);
  const x = { role: ROLES.has(role) ? role : "supplier", name: str(d.name, 200), country: str(d.country, 3).toUpperCase(), contact_name: str(d.contact_name, 160),
    email: str(d.email, 200), phone: intlPhone(str(d.phone, 40), str(d.country, 3)) || str(d.phone, 40), wechat: str(d.wechat, 60), website: str(d.website, 240), status: PARTY_STATUS.has(str(d.status, 20)) ? str(d.status, 20) : "candidate",
    note: str(d.note, 600), source: str(d.source, 300), last_contact: isDate(str(d.last_contact, 10)) ? str(d.last_contact, 10) : "" };
  if (!x.name) return { ok: false as const, error: "name is required" };
  return { ok: true as const, data: x, status: x.status };
}

export function clean(kind: Kind, d: Record<string, unknown>): { ok: true; data: Record<string, unknown>; status: string } | { ok: false; error: string } {
  if (kind === "party" || kind === "stage") return cleanProcess(kind, d);
  if (kind === "quote") {
    const q = {
      supplier: str(d.supplier, 160), country: str(d.country, 3).toUpperCase(), product: str(d.product, 200), grade: str(d.grade, 120),
      qty: numOrNull(d.qty), unit: str(d.unit, 20), unit_price: numOrNull(d.unit_price), currency: str(d.currency, 3).toUpperCase(),
      incoterm: str(d.incoterm, 3).toUpperCase(), named_place: str(d.named_place, 120), incoterm_edition: str(d.incoterm_edition, 12) || "",
      incl_freight: d.incl_freight === true, incl_insurance: d.incl_insurance === true, valid_until: str(d.valid_until, 10),
      payment_terms: str(d.payment_terms, 160), lead_time_days: numOrNull(d.lead_time_days), exclusions: str(d.exclusions, 300),
      availability: d.availability === "confirmed" ? "confirmed" : "unconfirmed", source_ref: str(d.source_ref, 300),
      supplier_claims: str(d.supplier_claims, 500),
    };
    if (!q.supplier) return { ok: false, error: "supplier is required" };
    if (Number.isNaN(q.unit_price) || Number.isNaN(q.qty) || Number.isNaN(q.lead_time_days)) return { ok: false, error: "price, quantity and lead time must be numbers" };
    if (q.unit_price != null && q.unit_price < 0) return { ok: false, error: "price cannot be negative" };
    if (q.currency && !/^[A-Z]{3}$/.test(q.currency)) return { ok: false, error: "currency is a 3-letter code (USD, EUR...)" };
    if (q.incoterm && !INCOTERMS.has(q.incoterm)) return { ok: false, error: "unknown Incoterm" };
    if (q.valid_until && !isDate(q.valid_until)) return { ok: false, error: "valid until is a date (YYYY-MM-DD)" };
    if (!q.source_ref) return { ok: false, error: "source of the quote is required (document, e-mail or call note)" };
    return { ok: true, data: q, status: "received" };
  }
  if (kind === "requirement") {
    const r = { item: str(d.item, 300), source_doc: str(d.source_doc, 160), page: str(d.page, 20), mandatory: d.mandatory !== false,
      status: REQ_STATUS.has(String(d.status)) ? String(d.status) : "unknown", evidence: str(d.evidence, 500), owner: str(d.owner, 80) };
    if (!r.item) return { ok: false, error: "requirement text is required" };
    if (r.status === "met" && !r.evidence) return { ok: false, error: "a met requirement needs its evidence (document or reference)" };
    return { ok: true, data: r, status: r.status };
  }
  if (kind === "economics") {
    const keys = ["role", "sale_price", "cost_goods", "freight", "insurance", "inspection", "duty_pct", "bank_pct", "fin_rate_pct", "deposit_pct",
      "deposit_day", "balance_day", "delivery_day", "customer_day", "commission_pct", "contingency_pct", "freight_in_quote", "insurance_in_quote", "notes"];
    const e: Record<string, unknown> = {};
    for (const k of keys) e[k] = ["role", "notes"].includes(k) ? str(d[k], 300) : ["freight_in_quote", "insurance_in_quote"].includes(k) ? d[k] === true : numOrNull(d[k]);
    if (Object.values(e).some((v) => typeof v === "number" && Number.isNaN(v))) return { ok: false, error: "economics inputs must be numbers" };
    e.role = e.role === "agent" ? "agent" : "principal";
    return { ok: true, data: e, status: "assumption" };
  }
  return { ok: false, error: "unknown record kind" };
}

export async function readDeal(dealId: string): Promise<{ records: DealRecord[]; versions: number }> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:J5000`]).catch(() => null))?.[0] || [];
  const latest = new Map<string, DealRecord>();
  let versions = 0;
  for (const r of rows) {
    if (!r || r[1] !== dealId) continue;
    versions++;
    let data: Record<string, unknown> = {};
    try { data = JSON.parse(r[6] || "{}"); } catch { data = {}; }
    const rec: DealRecord = { time: r[0] || "", deal_id: r[1], kind: r[2] as Kind, record_id: r[3] || "", version: Number(r[4]) || 1, status: r[5] || "", data, by: r[7] || "", source: r[8] || "" };
    const k = `${rec.kind}|${rec.record_id}`;
    const prev = latest.get(k);
    if (!prev || rec.version >= prev.version) latest.set(k, rec);
  }
  return { records: [...latest.values()].filter((r) => r.status !== "deleted"), versions };
}

export async function saveRecord(dealId: string, kind: Kind, recordId: string, version: number, status: string, data: Record<string, unknown>, by: string, note = "") {
  const time = new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 19);
  await appendRow(TAB, [time, dealId.slice(0, 120), kind, recordId.slice(0, 60), version, status, JSON.stringify(data).slice(0, 45000), by.slice(0, 120), "panel", note.slice(0, 200)]);
}

// The process board: every deal with a stage record, its latest stage and next step, and how many parties it has.
export async function pipeline(): Promise<{ deal_id: string; stage: Record<string, unknown>; parties: Record<string, number>; updated: string; by: string }[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:J5000`]).catch(() => null))?.[0] || [];
  const stage = new Map<string, { v: number; data: Record<string, unknown>; time: string; by: string }>();
  const party = new Map<string, Map<string, { v: number; role: string; status: string }>>();
  for (const r of rows) {
    if (!r || !r[1]) continue;
    const kind = r[2], v = Number(r[4]) || 1;
    let data: Record<string, unknown> = {};
    try { data = JSON.parse(r[6] || "{}"); } catch { data = {}; }
    if (kind === "stage") { const p = stage.get(r[1]); if (!p || v >= p.v) stage.set(r[1], { v, data, time: r[0] || "", by: r[7] || "" }); }
    if (kind === "party") {
      const m = party.get(r[1]) || new Map(); const p = m.get(r[3]);
      if (!p || v >= p.v) m.set(r[3], { v, role: String(data.role || ""), status: r[5] || "" });
      party.set(r[1], m);
    }
  }
  return [...stage.entries()].map(([id, s]) => {
    const counts: Record<string, number> = {};
    for (const p of (party.get(id) || new Map()).values()) if (p.status !== "deleted" && p.status !== "dropped") counts[p.role] = (counts[p.role] || 0) + 1;
    return { deal_id: id, stage: s.data, parties: counts, updated: s.time, by: s.by };
  }).sort((a, b) => String(b.updated).localeCompare(String(a.updated)));
}
