// What the system already holds about a company, gathered in code for the research role of the pipeline
// (lib/pipeline.ts, stage bd_research). No model and no web fetch: the supplier index (lib/index.ts suppliers(), the
// same rows the supplier search and the deal agent's search_suppliers read) and the stored business contact
// (lib/sheets.ts lookupContact, the deal agent's supplier_contact). Free to run.
//
// Every item is {fact, source, date}. The source names the dataset and the field the fact was read from. The date is
// the day the record was read, except where the record itself carries a date (the last public award). The index has
// no "last updated" stamp per record, so none is claimed: record_updated stays empty and the note says so.
//
// A company that is not in the index is found:false, and the case stops as no_material before any model call. A name
// that fits several records is also found:false, with the candidates listed: picking one would be a guess.
import { fpNorm, type Supplier } from "@/lib/index";
import { supplierKind } from "@/lib/panel";
import type { MaterialItem } from "@/lib/casestore";

export type Material = { found: boolean; company: string; country: string; website: string; contact_email: string; record_updated: string; note: string; candidates: string[]; items: MaterialItem[] };
export type MaterialDeps = {
  suppliers: () => Promise<{ rows: Supplier[]; error?: string }>;
  /** the stored business contact of one supplier by its exact name and ISO3 country; null when there is none */
  contact: (name: string, country: string) => Promise<Record<string, string> | null>;
  now: () => number;
};

export const INDEX_SOURCE = "supplier index (data/web/suppliers.enc)", UNIVERSE_SOURCE = "Supplier Universe sheet, tab Suppliers";
export const MAX_ITEMS = 30, MAX_MATERIAL_BYTES = 7_500; // the research role reads at most 8,000 bytes of material
const cut = (v: unknown, n: number) => { const s = String(v ?? "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const isDay = (v: unknown) => /^\d{4}-\d{2}-\d{2}/.test(String(v || ""));

/** The facts of one index row. `tag` tells records apart when a name has more than one. */
function rowFacts(s: Supplier, today: string, tag: string): MaterialItem[] {
  const out: MaterialItem[] = [];
  const add = (fact: string, fields: string, date = today) => { if (fact && fields && date) out.push({ fact: cut(tag + fact, 400), source: `${INDEX_SOURCE}, ${fields}`, date }); };
  add(`Listed as "${cut(s.n, 160)}"${s.c ? `, country ${s.c}` : ""}${s.rg ? `, region ${s.rg}` : ""}.`, "fields n (name), c (country), rg (region)");
  if (s.p) add(`Products on record: ${cut(s.p, 300)}.`, "field p (products)");
  if (s.s || s.s2) add(`${s.s ? `Main sector on record: ${s.s}` : "No main sector on record"}${s.s2 ? `; other sectors: ${cut(s.s2, 160)}` : ""}.`, "fields s (main sector), s2 (other sectors)");
  if (s.ty || s.td) add(`Type on record: ${s.ty || "not stated"}${s.td === "yes" ? "; flagged as a trader" : ""}.`, "fields ty (type), td (trader)");
  const kind = supplierKind(s);
  add(kind ? `Reads as a ${kind === "maker" ? "manufacturer" : "trader"} by the system's naming rule. This is a rule over the record's wording, not a verified fact.` : "The record does not say whether this is a manufacturer or a trader.", "rule supplierKind over fields ty, td, n, p, in");
  if (s.tr) add(`Tier ${s.tr} in the system's ranking${s.why ? `; reason on record: ${cut(s.why, 200)}` : ""}.`, "fields tr (tier), why (tier reason)");
  if (s.web) add(`Website on record: ${cut(s.web, 200)}${s.wb ? ` (basis: ${cut(s.wb, 120)})` : ""}.`, "fields web (website), wb (basis of the website)");
  if (s.hs || s.hd) add(`Customs headings on record: ${cut(s.hd, 220) || "names not stored"}${s.hs ? ` (HS ${cut(s.hs, 120)})` : ""}.`, "fields hs (HS codes), hd (HS names)");
  if (s.sh) add(`Export shipments in the last 12 months on record: ${s.sh}.`, "field sh (shipments, 12 months)");
  if (s.x) add(`Export record: ${cut(s.x, 200)}.`, "field x (exports)");
  if (s.w || s.u) add(`Public contract awards on record: ${s.w || 0}${s.u ? `, estimated USD ${Math.round(Number(s.u)).toLocaleString("en-US")}` : ""}${s.bc ? `; buyer countries: ${cut(s.bc, 120)}` : ""}${s.lw ? `; last award ${cut(s.lw, 20)}` : ""}.`,
    "fields w (awards), u (won, USD estimate), bc (buyer countries), lw (last award)", isDay(s.lw) ? String(s.lw).slice(0, 10) : today);
  if (s.sp) add(`Supplied under public contracts: ${cut(s.sp, 300)}.`, "field sp (supplied)");
  if (s.cm) add(`Commodity groups on record: ${cut(s.cm, 160)}.`, "field cm (commodities)");
  if (s.in) add(`Industries on record: ${cut(s.in, 200)}.`, "field in (industries)");
  if (s.ds) add(`Listed in the trade directory ${cut(s.ds, 120)}${s.du ? ` (${cut(s.du, 200)})` : ""}.`, "fields ds (directory), du (listing)");
  if (s.em || s.nt) add(`Size signals on record: ${[s.em ? `employees ${cut(s.em, 40)}` : "", s.nt ? `notable company: ${cut(s.nt, 80)}` : ""].filter(Boolean).join("; ")}.`, "fields em (employees), nt (notable)");
  if (s.rc) add("The record carries an open conflict flag: two sources disagree about this company and it was not resolved.", "field rc (open conflict)");
  // a directory prints a person next to the address; only the address itself is passed on
  const dir = String(s.ct || "").match(EMAIL) || [];
  if (dir.length) add(`Contact e-mail printed by an official directory: ${dir.slice(0, 2).join(", ")}.`, "field ct (directory contact)");
  return out;
}

export async function gatherMaterial(deps: MaterialDeps, q: { company: string; country?: string }): Promise<Material> {
  const today = new Date(deps.now()).toISOString().slice(0, 10), asked = cut(q.company, 160), typed = cut(q.country, 60);
  const none = (note: string, candidates: string[] = []): Material => ({ found: false, company: asked, country: typed, website: "", contact_email: "", record_updated: "", note, candidates, items: [] });
  const key = fpNorm(asked);
  if (!key) return none("no company name was given");
  let all: { rows: Supplier[]; error?: string };
  try { all = await deps.suppliers(); } catch (e) { return none(`the supplier index could not be read: ${cut((e as Error)?.message || e, 120)}`); }
  if (!all.rows.length) return none(all.error ? `the supplier index could not be read: ${cut(all.error, 120)}` : "the supplier index is empty");
  // the country narrows the search only as an ISO3 code, which is what the index stores; a country typed as a name is kept on the case and not used
  const iso = /^[A-Za-z]{3}$/.test(typed) ? typed.toUpperCase() : "";
  const pool = iso ? all.rows.filter((s) => s.c === iso) : all.rows;
  const label = (s: Supplier) => `${s.n}${s.c ? ` (${s.c})` : ""}`;
  const distinct = (rows: Supplier[]) => [...new Set(rows.map(label))];
  let hit = pool.filter((s) => fpNorm(s.n) === key), how = "exact name";
  if (!hit.length) {
    const words = key.split(" ");
    hit = pool.filter((s) => { const w = fpNorm(s.n).split(" "); return words.every((x) => w.includes(x)); });
    how = "every word of the name asked for";
    if (!hit.length) return none(`"${asked}"${iso ? ` in ${iso}` : ""} is not in the supplier index`);
  }
  const names = distinct(hit);
  if (names.length > 1) return none(`"${asked}" fits ${names.length} companies in the supplier index; give the exact name${iso ? "" : " and the ISO3 country code"}`, names.slice(0, 8));

  const rows = hit.slice(0, 3), s = rows[0];
  const items: MaterialItem[] = [];
  if (how !== "exact name") items.push({ fact: `The record was matched by ${how} ("${asked}"), not by the exact name. Check that this is the company meant.`, source: `${INDEX_SOURCE}, field n (name)`, date: today });
  if (hit.length > 1) items.push({ fact: `The index holds ${hit.length} records under this name; the facts below come from the first ${rows.length}.`, source: `${INDEX_SOURCE}, field n (name)`, date: today });
  rows.forEach((r, i) => items.push(...rowFacts(r, today, rows.length > 1 ? `Record ${i + 1}: ` : "")));

  let email = "", website = cut(s.web, 200), contactNote = "";
  try {
    const c = s.c ? await deps.contact(s.n, s.c) : null;
    const mails = String(c?.email || "").match(EMAIL) || [];
    if (mails.length || c?.phone) items.push({ fact: `Published business contact on record: ${[mails.length ? `e-mail ${mails.slice(0, 2).join(", ")}` : "", c?.phone ? `phone ${cut(c.phone, 40)}` : ""].filter(Boolean).join("; ")}.`, source: `${UNIVERSE_SOURCE}, columns AA (email), AB (phone)`, date: today });
    if (c?.website) { items.push({ fact: `Official website on record: ${cut(c.website, 200)}${c.website_source ? ` (source: ${cut(c.website_source, 120)})` : ""}.`, source: `${UNIVERSE_SOURCE}, columns AC (website), AD (website source)`, date: today }); website ||= cut(c.website, 200); }
    email = mails[0] || "";
    if (!c) contactNote = " No business contact is stored for it.";
  } catch { contactNote = " The stored contact could not be read."; }
  email ||= (String(s.ct || "").match(EMAIL) || [])[0] || "";

  // what does not fit the research role's input is left out whole, never cut in the middle of a fact
  let kept = items.slice(0, MAX_ITEMS);
  while (kept.length > 1 && Buffer.byteLength(materialText(kept), "utf8") > MAX_MATERIAL_BYTES) kept = kept.slice(0, -1);
  const dropped = items.length - kept.length;
  return { found: true, company: s.n, country: s.c || typed, website, contact_email: email, record_updated: "", candidates: [], items: kept,
    note: `Read from the supplier index on ${today} (matched by ${how}). The index carries no per-record update date; each fact shows the day it was read, or the record's own date.${contactNote}${dropped > 0 ? ` ${dropped} further facts did not fit and were left out.` : ""}` };
}

/** The material as the research role receives it: one numbered line per fact, with its source and date. */
export function materialText(items: MaterialItem[]): string {
  return items.map((m, i) => `${i + 1}. ${m.fact} [source: ${m.source}; date: ${m.date}]`).join("\n");
}
