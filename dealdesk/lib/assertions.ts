import { createHash } from "crypto";
import { DEFAULT_WS } from "@/lib/auth";

// The assertions ledger (spec sections 6 and 7): one row per version of one claim about one entity. Rows are
// append-only; a correction, dispute or rejection is a new row whose `supersedes` points at the row it replaces.
// Nothing is ever deleted or edited in place, so a quarantined claim keeps its history and the entity keeps its
// other properties. Everything in this file is pure (no I/O): storage lives in assertionstore.ts.
//
// Workspaces: ws is the organisation that owns the row; "public" rows are reusable public knowledge visible to
// every workspace. A row from workspace A is never visible to workspace B.

export const PUBLIC_WS = "public";
export const ENTITY_KINDS = ["supplier", "buyer", "client", "project", "product"] as const;
export const STATUSES = ["observed", "inferred", "disputed", "rejected", "expired"] as const;
export type EntityKind = (typeof ENTITY_KINDS)[number];
export type Status = (typeof STATUSES)[number];

export type Evidence = {
  url?: string;         // where the fact was read (canonicalised on write, original kept in `url_raw`)
  url_raw?: string;
  doc_hash?: string;    // sha256 (or any stable id) of the document the fact was read from
  publisher?: string;   // who published it (company site, regulator, registry, newspaper, client deck)
  published?: string;   // ISO date the source was published, if known
  collected?: string;   // ISO date the source was read
  verified?: string;    // ISO date a person or a model checked the fact against the source
  excerpt?: string;     // the sentence(s) that support the value, verbatim, bounded
  method?: string;      // how it was extracted: "human entry", "web check, model agent", "verified caps import", ...
  version?: string;     // extractor or prompt version
  reason?: string;      // set on disputed / rejected rows: why
};

export type Assertion = {
  id: string;
  ws: string;
  entity_kind: EntityKind;
  entity_key: string;   // normaliseEntityKey(name, country) or an explicit id
  property: string;     // supplies, legal_id, website, export_to, capacity, certification, ...
  value: string;
  unit: string;         // unit or currency code, "" when not applicable
  status: Status;
  evidence: Evidence;
  independent_sources: number;  // mirrored copies of one document count once
  review_method: string;        // "human entry", "human quarantine", "human report (email)", "web check, model agent", ...
  reviewed_at: string;
  reviewed_by: string;
  supersedes: string;   // id of the row this one replaces, "" for a first version
  expires: string;      // ISO date after which the fact is stale (shown as expired on read), "" for none
  created: string;      // ISO timestamp the row was appended
};

// Column order of the 'Assertions' tab (header row). JSON in the evidence cell.
export const COLUMNS = ["id", "ws", "entity_kind", "entity_key", "property", "value", "unit", "status", "evidence", "independent_sources",
  "review_method", "reviewed_at", "reviewed_by", "supersedes", "expires", "created"] as const;

const LEGAL = /\b(co|corp|corporation|inc|ltd|limited|llc|gmbh|sa|s\.a\.|spa|s\.p\.a\.|srl|bv|ag|plc|pte|pvt|private|company|the)\b/g;

// "ACME Steel Ltd." + "tr" -> "acme steel|TR". Matches the supplier search's dedupe key so a verified capability and
// a search hit name the same entity. An explicit id ("id:...") is kept as given.
export function normaliseEntityKey(name: string, country = ""): string {
  const n = String(name || "").trim();
  if (/^id:/i.test(n)) return n;
  const base = n.toLowerCase().replace(LEGAL, "").replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  return `${base}|${String(country || "").trim().toUpperCase().slice(0, 3)}`;
}

// Lower-cased host without "www.", path without a trailing slash, no fragment, no utm_* / tracking parameters,
// remaining parameters sorted. Returns "" for anything that is not an http(s) URL.
export function canonicalUrl(u: string): string {
  let p: URL;
  try { p = new URL(String(u || "").trim()); } catch { return ""; }
  if (p.protocol !== "http:" && p.protocol !== "https:") return "";
  const host = p.hostname.toLowerCase().replace(/^www\./, "");
  const path = p.pathname.replace(/\/+$/, "") || "";
  const keep = [...p.searchParams.entries()].filter(([k]) => !/^(utm_|fbclid|gclid|mc_|ref$|_ga$)/i.test(k)).sort((a, b) => a[0].localeCompare(b[0]) || a[1].localeCompare(b[1]));
  const q = keep.length ? "?" + keep.map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`).join("&") : "";
  return `https://${host}${path}${q}`;
}

// host + path only: the unit of "one source" for mirror detection (query strings and protocol do not make a new source)
export function sourceKey(e: Evidence): string {
  const c = canonicalUrl(e.url || e.url_raw || "");
  if (!c) return "";
  const p = new URL(c);
  return `${p.hostname}${p.pathname}`;
}

// The supporting text reduced to letters and digits, for comparing copies of one document published on several
// sites. Shorter than 80 characters is too little to tell a copy from two sources saying the same short thing.
const SAME_TEXT_MIN = 80;
function textKey(e: Evidence): string {
  const t = String(e.excerpt || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
  return t.length >= SAME_TEXT_MIN ? t : "";
}

// Two pieces of evidence are the same source when they carry the same document hash, point at the same host+path,
// or quote the same text (a press release republished by a wire service or a news site: one copy's excerpt equals
// or contains the other's). A rewritten article that repeats the claim in other words is NOT detected here.
export function isMirror(a: Evidence, b: Evidence): boolean {
  if (a.doc_hash && b.doc_hash && a.doc_hash === b.doc_hash) return true;
  const ka = sourceKey(a), kb = sourceKey(b);
  if (ka && kb && ka === kb) return true;
  const ta = textKey(a), tb = textKey(b);
  return Boolean(ta && tb && (ta.includes(tb) || tb.includes(ta)));
}

// Evidence grouped by source family: every member of a family is a copy of another member (same document hash,
// same host+path or the same text), directly or through a third copy. One family is one confirmation.
export function evidenceFamilies(list: Evidence[]): Evidence[][] {
  const fams: Evidence[][] = [];
  for (const e of list) {
    const hit = fams.filter((f) => f.some((k) => isMirror(k, e)));
    if (!hit.length) { fams.push([e]); continue; }
    hit[0].push(e);
    for (const other of hit.slice(1)) { hit[0].push(...other); fams.splice(fams.indexOf(other), 1); }
  }
  return fams;
}

// How many independent sources a set of evidence represents (mirrors collapse to one).
export function countIndependent(list: Evidence[]): number {
  return evidenceFamilies(list).length;
}

export const sha256 = (s: string) => createHash("sha256").update(s).digest("hex");
export function newId(): string {
  return `A-${Date.now().toString(36).toUpperCase()}-${Math.random().toString(36).slice(2, 7).toUpperCase()}`;
}

const isHuman = (a: Assertion) => /^human/i.test(a.review_method || "");
const groupKey = (a: Assertion) => `${a.ws}\u0001${a.entity_key}\u0001${a.property}\u0001${a.value}`;

// Latest non-superseded version per (ws, entity_key, property, value). A human-reviewed version outranks a model
// one regardless of order; among equals the newest created (then reviewed_at) wins. Input is never mutated.
export function resolve(rows: Assertion[]): Assertion[] {
  const superseded = new Set(rows.map((r) => r.supersedes).filter(Boolean));
  const groups = new Map<string, Assertion[]>();
  for (const r of rows) {
    if (superseded.has(r.id)) continue;
    const k = groupKey(r);
    groups.set(k, [...(groups.get(k) || []), r]);
  }
  const out: Assertion[] = [];
  for (const g of groups.values()) {
    const best = [...g].sort((a, b) => (Number(isHuman(b)) - Number(isHuman(a))) || b.created.localeCompare(a.created) || b.reviewed_at.localeCompare(a.reviewed_at))[0];
    out.push(best);
  }
  return out;
}

// Rows past their `expires` date are returned as expired copies; stored rows are never changed. A rejected or
// disputed row keeps its status (a rejection does not become merely stale).
export function expire(rows: Assertion[], now = new Date()): Assertion[] {
  const today = now.toISOString().slice(0, 10);
  return rows.map((r) => (r.expires && r.expires.slice(0, 10) < today && (r.status === "observed" || r.status === "inferred")) ? { ...r, status: "expired" as Status } : r);
}

// Builds the superseding row that quarantines one claim. Only that claim is affected: every other property of the
// entity is untouched. Returns null when the id is unknown.
export function quarantine(rows: Assertion[], id: string, reason: string, by: string, status: "disputed" | "rejected" = "disputed", now = new Date()): Assertion | null {
  const src = rows.find((r) => r.id === id);
  if (!src) return null;
  const ts = now.toISOString();
  return {
    ...src,
    id: newId(),
    status,
    evidence: { ...src.evidence, reason: String(reason || "").slice(0, 500) },
    review_method: "human quarantine",
    reviewed_at: ts.slice(0, 10),
    reviewed_by: by,
    supersedes: src.id,
    created: ts,
  };
}

// Rows a workspace may read: its own plus public knowledge. Legacy rows without a ws belong to the original owner.
export function visibleTo(rows: Assertion[], ws: string): Assertion[] {
  return rows.filter((r) => (r.ws || DEFAULT_WS) === ws || r.ws === PUBLIC_WS);
}

export function filterRows(rows: Assertion[], f: { entity_key?: string; property?: string; status?: string }): Assertion[] {
  return rows.filter((r) => (!f.entity_key || r.entity_key === f.entity_key) && (!f.property || r.property === f.property) && (!f.status || r.status === f.status));
}

// Serialisation to and from one sheet row (COLUMNS order). Bad JSON in the evidence cell becomes {} rather than a crash.
export function toRow(a: Assertion): (string | number)[] {
  return [a.id, a.ws, a.entity_kind, a.entity_key, a.property, a.value, a.unit, a.status, JSON.stringify(a.evidence).slice(0, 45000), a.independent_sources,
    a.review_method, a.reviewed_at, a.reviewed_by, a.supersedes, a.expires, a.created];
}
export function fromRow(r: (string | number)[]): Assertion | null {
  const v = (i: number) => String(r[i] ?? "").trim();
  if (!v(0) || !v(3) || !v(4)) return null;
  let ev: Evidence = {};
  try { ev = JSON.parse(v(8) || "{}"); } catch { ev = {}; }
  const kind = (ENTITY_KINDS as readonly string[]).includes(v(2)) ? (v(2) as EntityKind) : "supplier";
  const status = (STATUSES as readonly string[]).includes(v(7)) ? (v(7) as Status) : "inferred";
  return { id: v(0), ws: v(1) || DEFAULT_WS, entity_kind: kind, entity_key: v(3), property: v(4), value: v(5), unit: v(6), status, evidence: ev,
    independent_sources: Math.max(0, Number(v(9)) || 0), review_method: v(10), reviewed_at: v(11), reviewed_by: v(12), supersedes: v(13), expires: v(14), created: v(15) };
}
export function fromGrid(grid: string[][]): Assertion[] {
  if (!grid.length) return [];
  const start = String(grid[0][0] || "").toLowerCase() === "id" ? 1 : 0;
  return grid.slice(start).map(fromRow).filter((x): x is Assertion => Boolean(x));
}

// Builds a fresh assertion from validated fields (the API and the import both use this).
export function makeAssertion(p: {
  ws: string; entity_kind: EntityKind; entity_key: string; property: string; value: string; unit?: string; status: "observed" | "inferred";
  evidence: Evidence; review_method: string; reviewed_by: string; expires?: string; now?: Date; id?: string;
}): Assertion {
  const ts = (p.now || new Date()).toISOString();
  const raw = String(p.evidence.url || "").slice(0, 300);
  const canon = canonicalUrl(raw);
  const ev: Evidence = { ...p.evidence, url: canon || raw, url_raw: raw, collected: p.evidence.collected || ts.slice(0, 10) };
  return { id: p.id || newId(), ws: p.ws, entity_kind: p.entity_kind, entity_key: p.entity_key, property: p.property.slice(0, 40), value: String(p.value).slice(0, 500),
    unit: String(p.unit || "").slice(0, 12), status: p.status, evidence: ev, independent_sources: ev.url || ev.doc_hash ? 1 : 0,
    review_method: p.review_method, reviewed_at: ts.slice(0, 10), reviewed_by: p.reviewed_by, supersedes: "", expires: p.expires || "", created: ts };
}

// One-way import of the UNIVERSE 'Verified capabilities' tab (header: supplier, country, product, label, evidence_url,
// evidence_note, checked, method, source_query). yes -> observed, related -> inferred, no -> rejected, unknown is
// not a fact and is not imported. Public knowledge (ws "public") since the tab is shared by every workspace.
// Ids are content hashes, so running the import twice produces the same rows (the caller dedupes on id).
export function assertionsFromVerifiedCaps(grid: string[][], now = new Date()): Assertion[] {
  if (grid.length < 2) return [];
  const h = grid[0].map((x) => String(x).toLowerCase().trim()), ix = (k: string) => h.indexOf(k);
  const out: Assertion[] = [];
  for (const r of grid.slice(1)) {
    const g = (k: string) => String(r[ix(k)] ?? "").trim();
    const supplier = g("supplier"), product = g("product"), label = g("label").toLowerCase(), method = g("method"), checked = g("checked");
    if (!supplier || !product) continue;
    const status: Status | null = label === "yes" ? "observed" : label === "related" ? "inferred" : label === "no" ? "rejected" : null;
    if (!status) continue;
    const url = g("evidence_url");
    const human = /^human/i.test(method);
    const id = `A-VC-${sha256([supplier, g("country"), product, label, url, checked, method].join("|")).slice(0, 12).toUpperCase()}`;
    const ev: Evidence = { url: canonicalUrl(url) || url, url_raw: url, excerpt: g("evidence_note").slice(0, 500), collected: checked, verified: checked,
      method: method || "verified caps import", version: "verified-caps-1" };
    const ts = (checked ? `${checked}T00:00:00.000Z` : now.toISOString());
    out.push({ id, ws: PUBLIC_WS, entity_kind: "supplier", entity_key: normaliseEntityKey(supplier, g("country")), property: "supplies", value: product, unit: "", status,
      evidence: ev, independent_sources: /^https?:\/\//.test(url) ? 1 : 0, review_method: human ? method : "web check, model agent", reviewed_at: checked,
      reviewed_by: human ? (method.match(/\(([^)]+)\)/)?.[1] || "human") : "model", supersedes: "", expires: "", created: ts });
  }
  return out;
}
