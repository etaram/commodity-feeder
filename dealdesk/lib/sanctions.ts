import { RAW_ROOT } from "@/lib/rawbase";
// Screening of a company name against the official sanctions lists (OFAC, UN Security Council, EU), indexed daily by
// the sanctions workflow into data/leads/sanctions.json. Name matching only: a hit is a lead to verify, never a verdict.
type Ent = [string[], string, string, string, string];
let mem: { at: number; updated: string; ents: Ent[]; toks: string[][][] } | null = null;

const STOP = new Set(["ltd", "limited", "llc", "inc", "incorporated", "co", "company", "corp", "corporation", "gmbh", "sa", "sarl", "ag", "bv", "nv", "plc", "jsc", "ojsc", "pjsc", "ooo", "zao", "oao", "llp", "lp", "pte", "pvt", "private", "public", "the", "of", "and", "for", "international", "group", "holding", "holdings", "trading", "general", "services", "industries", "industrial", "enterprises", "enterprise", "ab", "as", "oy", "spa", "srl", "kg", "ltda", "fze", "fzc", "fzco", "lc"]);
export const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9Ѐ-ӿ֐-׿؀-ۿ一-鿿 ]+/g, " ").replace(/\s+/g, " ").trim();
const toks = (s: string) => norm(s).split(" ").filter((t) => t && !STOP.has(t));

async function load() {
  if (mem && Date.now() - mem.at < 6 * 3600_000) return mem;
  const r = await fetch(`${RAW_ROOT}/data/leads/sanctions.json`, { cache: "no-store", signal: AbortSignal.timeout(20000) });
  if (!r.ok) throw new Error("sanctions index HTTP " + r.status);
  const j = await r.json();
  const ents: Ent[] = j.e || [];
  mem = { at: Date.now(), updated: j.updated || "", ents, toks: ents.map((e) => e[0].map(toks)) };
  return mem;
}

type Hit = { strength: 1 | 2 | 3; via: string; list: string; program: string; kind: string; ref: string };
/** Name hits of one query against the loaded index, strongest first. Pure. */
function hitsFor(name: string, m: { ents: Ent[]; toks: string[][][] }): Hit[] {
  const q = toks(name);
  if (!q.length) return [];
  const qs = new Set(q), qn = q.join(" ");
  const hits: Hit[] = [];
  m.ents.forEach((e, i) => {
    let best = 0, via = "";
    m.toks[i].forEach((t, k) => {
      if (!t.length) return;
      const tn = t.join(" ");
      let s = 0;
      if (tn === qn) s = 3;
      else if (q.length >= 2 && q.every((x) => t.includes(x)) && t.length <= q.length + 1) s = 2;
      else if (t.length >= 2 && t.every((x) => qs.has(x)) && q.length <= t.length + 2) s = 1;
      if (s > best) { best = s; via = e[0][k]; }
    });
    if (best) hits.push({ strength: best as 1 | 2 | 3, via, list: e[1], program: e[2], kind: e[3], ref: e[4] });
  });
  return hits.sort((a, b) => b.strength - a.strength);
}
const STRENGTH = { 3: "STRONG name match", 2: "Close name match", 1: "Partial name match" } as const;

export async function sanctionsFacts(name: string): Promise<string> {
  if (!toks(name).length) return "";
  const m = await load();
  const hits = hitsFor(name, m).map((h) => `- ${STRENGTH[h.strength]}: "${h.via}" on ${h.list} (${h.kind}${h.program ? ", program " + h.program : ""}, ref ${h.ref})`);
  const head = `Sanctions screening (OFAC SDN and consolidated, UN Security Council, EU and UK consolidated; index updated ${m.updated} UTC; screening lead only, not a compliance clearance; name matching only, verify identity, address and registration number before concluding):`;
  return hits.length ? [head, ...hits.slice(0, 6)].join("\n") : `${head}\n- No name match found for "${name}" in those lists. This is a screening lead, not a compliance clearance, and it does not cover the Swiss, Canadian or Israeli lists, nor aliases not published.`;
}

// ---- structured screen of a deal's parties (lib/routemap.ts, lib/missionrun.ts) -------------------------------------
// Status vocabulary of the release. This module produces NOT_CHECKED, CHECKED_NO_ISSUE, FAILED and STALE.
// VERIFIED is never produced by code: only a qualified person's review can verify a party, and nothing records one yet.
// CHECKED_NO_ISSUE means "checked, no candidate match on <date>" by name matching against the indexed lists. It is NOT a
// clearance. FAILED means at least one candidate name match of any strength: qualified review required. A candidate is
// never cleared here.
export const SCREEN_STATUSES = ["NOT_CHECKED", "CHECKED_NO_ISSUE", "FAILED", "STALE", "VERIFIED"] as const;
export type ScreenStatus = (typeof SCREEN_STATUSES)[number];
export type ScreenParty = { role: string; name: string };
export type ScreenCandidate = { role: string; name: string; matched: string; strength: string; list: string; program: string; ref: string };
export type PartyScreen = { status: ScreenStatus; label: string; checked_on: string | null; index_updated: string; screened: ScreenParty[]; candidates: ScreenCandidate[]; clearance: false };
export type SanctionsIndex = { updated: string; ents: Ent[] };
export const SANCTIONS_SOURCE = "sanctions index data/leads/sanctions.json (OFAC, UN Security Council, EU, UK; name matching only)";
export const STALE_AFTER_DAYS = 3; // the index is rebuilt daily; older than this, a "no match" does not count

const updatedMs = (v: string) => { const t = Date.parse(/^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}/.test(v) && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(v) ? v.replace(" ", "T") + "Z" : v); return Number.isFinite(t) ? t : null; };

/** Screen named parties against an index. Pure: the caller supplies the index (null = the lists could not be read) and the time. */
export function screenWith(index: SanctionsIndex | null, parties: ScreenParty[], now: string): PartyScreen {
  const seen = new Set<string>();
  const list = parties.map((p) => ({ role: String(p.role || "party"), name: String(p.name || "").trim() })).filter((p) => { const k = norm(p.name); if (!toks(p.name).length || seen.has(k)) return false; seen.add(k); return true; });
  const base = { checked_on: null, index_updated: index?.updated || "", screened: [] as ScreenParty[], candidates: [] as ScreenCandidate[], clearance: false as const };
  if (!index) return { ...base, status: "NOT_CHECKED", label: "not checked: the sanctions lists could not be read" };
  if (!list.length) return { ...base, status: "NOT_CHECKED", label: "not checked: no party name to screen" };
  const m = { ents: index.ents, toks: index.ents.map((e) => e[0].map(toks)) };
  const day = String(now).slice(0, 10);
  const candidates = list.flatMap((p) => hitsFor(p.name, m).slice(0, 6).map((h) => ({ role: p.role, name: p.name, matched: h.via, strength: STRENGTH[h.strength], list: h.list, program: h.program, ref: h.ref })));
  const done = { ...base, checked_on: day, screened: list, candidates };
  if (candidates.length) return { ...done, status: "FAILED", label: `sanctions alert: ${candidates.length} candidate name match(es) on ${day} for ${[...new Set(candidates.map((c) => c.name))].join("; ")}. Qualified review required; a candidate is never cleared automatically` };
  const up = updatedMs(index.updated), nowMs = Date.parse(now);
  if (up === null || !Number.isFinite(nowMs) || nowMs - up > STALE_AFTER_DAYS * 86_400_000)
    return { ...done, status: "STALE", label: `not checked against current lists: the index was last updated ${index.updated || "at an unknown time"}; no candidate match in that older copy, which does not count` };
  return { ...done, status: "CHECKED_NO_ISSUE", label: `checked, no candidate match on ${day} (name matching only, index updated ${index.updated} UTC; this is not a clearance)` };
}

/** The same screen against the live index. Never throws: an unreadable index reads as NOT_CHECKED. */
export async function screenParties(parties: ScreenParty[], now: string): Promise<PartyScreen> {
  let index: SanctionsIndex | null = null;
  // bounded: a slow index never holds the page; no answer in time reads as "not checked"
  let timer: ReturnType<typeof setTimeout> | undefined;
  try { const m = await Promise.race([load(), new Promise<never>((_, no) => { timer = setTimeout(() => no(new Error("timeout")), 8000); })]); index = { updated: m.updated, ents: m.ents }; } catch { index = null; }
  finally { if (timer) clearTimeout(timer); }
  return screenWith(index, parties, now);
}
