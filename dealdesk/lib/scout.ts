// Scouts: the part of the team that opens opportunities by itself. This file is the pure logic: given candidate
// signals (fresh contract winners from the awards index and new open tenders), what was already handled (the tab
// 'Scout Seen'), the owner's focus and the limits, it decides which signals are pursued, why, and which team member
// each one is assigned to, and it writes the brief the deal agent run starts from. No network, no sheet, no model:
// app/api/cron/scout (through lib/scoutrun.ts) loads the data, records every decision and starts the runs.
//
// A score is a sum of named points. Every point comes from a field the data really has, and its reason is kept next
// to it, so the owner can read why a signal was chosen. The points are fixed sizes chosen by hand, not measured effects.
import { member, type Member } from "@/lib/team";

export const SCOUT_SEEN = "Scout Seen";
export type SignalKind = "winner" | "tender";
export type Signal = {
  kind: SignalKind; id: string; title: string; country: string; buyer: string; value_usd: number; link?: string; source?: string;
  // winner signals (lib/index.ts Winner)
  date?: string; winner?: string; winner_country?: string; winner_kind?: string; needs?: string[]; commodity?: string;
  website?: string; contact?: string; contact_page?: string;
  // tender signals (the tender store, lib/panel.ts allTenders)
  days_left?: number | null; fit?: number | null; sector?: string; access?: string; decision?: string; nature?: string;
  // the buyer's record: awards counted in the award data (buyer_profile for winners, buyer_awards_12m for tenders); null = not known
  buyer_awards?: number | null;
};
/** What the owner wants scouted: product or sector words, partner countries, excluded countries (lib/strategy.ts). Empty = no filter. */
export type Focus = { words: string[]; partners: string[]; excluded: string[] };
export const NO_FOCUS: Focus = { words: [], partners: [], excluded: [] };

// ---- 'Scout Seen' ------------------------------------------------------------------------------------------
// Columns: A time, B workspace, C signal kind, D signal id, E score, F decision, G run id, H assignee ids, I label,
// J reasons, K deal id. Append-only; the latest row of a signal is its state.
export type SeenRow = { time: string; ws: string; kind: string; id: string; score: number; decision: string; run_id: string; assignees: string[]; label: string; reasons: string[]; deal_id: string };
export const PURSUED = "pursued", LIMIT = "skipped: limit", START_FAILED = "skipped: start failed";
/** A decision that may be taken again later: the signal itself was fine, the day's limits or a fault stopped it. */
export const transient = (decision: string) => decision === LIMIT || decision === START_FAILED;
const cut = (v: unknown, n: number) => String(v ?? "").replace(/[\r\n\t]+/g, " ").slice(0, n);
export function seenToCells(r: SeenRow): (string | number)[] {
  return [r.time, r.ws, r.kind, cut(r.id, 120), Math.round(r.score), cut(r.decision, 60), cut(r.run_id, 40), r.assignees.join(","), cut(r.label, 200), cut(r.reasons.join(" | "), 700), cut(r.deal_id, 60)];
}
export function cellsToSeen(c: string[] | undefined): SeenRow | null {
  if (!c || !c[0] || !c[3] || (c[2] !== "winner" && c[2] !== "tender")) return null;
  return { time: c[0], ws: c[1] || "", kind: c[2], id: c[3], score: Number(c[4]) || 0, decision: c[5] || "", run_id: c[6] || "",
    assignees: String(c[7] || "").split(",").map((x) => x.trim()).filter(Boolean), label: c[8] || "", reasons: String(c[9] || "").split(" | ").filter(Boolean), deal_id: c[10] || "" };
}
const keyOf = (kind: string, id: string) => `${kind}:${id}`;
/** The latest row of every signal of one workspace. */
export function latestSeen(rows: SeenRow[], ws: string): Map<string, SeenRow> {
  const m = new Map<string, SeenRow>();
  for (const r of rows) if (r.ws === ws) m.set(keyOf(r.kind, r.id), r);
  return m;
}
/** Runs the scouts started on one UTC day: signals whose row says pursued and carries that day. */
export function pursuedOn(rows: SeenRow[], ws: string, day: string): number {
  return new Set(rows.filter((r) => r.ws === ws && r.decision === PURSUED && r.time.startsWith(day)).map((r) => keyOf(r.kind, r.id))).size;
}

// ---- freshness ---------------------------------------------------------------------------------------------
const DAY = 864e5;
/** Whole days from an ISO date (YYYY-MM-DD) to now; NaN when the date cannot be read or lies in the future by more than a day. */
export function ageDays(date: string | undefined, now: number): number {
  const t = /^\d{4}-\d{2}-\d{2}/.test(String(date || "")) ? Date.parse(String(date).slice(0, 10) + "T00:00:00Z") : NaN;
  if (!Number.isFinite(t) || t - now > DAY) return NaN;
  return Math.max(0, Math.floor((now - t) / DAY));
}
const norm = (s: unknown) => String(s ?? "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
/** A stable id for a winner row: the index id when it has one, otherwise the winner, the title and the date. */
export function winnerSignalId(w: { id?: string; w?: string[]; t?: string; d?: string }): string {
  const id = String(w.id || "").trim();
  if (id) return id.slice(0, 100);
  return `${norm(w.w?.[0]).slice(0, 40)}|${norm(w.t).slice(0, 50)}|${String(w.d || "").slice(0, 10)}`;
}

// ---- who takes it ------------------------------------------------------------------------------------------
// The supplier-relations regions of lib/team.ts by country (ISO3; the lists follow leads/regions.py). North America and
// Oceania go to the Middle East and North Africa member, as her role in team.ts says; Israel is home and goes there too.
const REGION_MEMBER: [string, string][] = [
  ["relations_asia", "CHN HKG JPN KOR MAC MNG PRK TWN BRN IDN KHM LAO MMR MYS PHL SGP THA TLS VNM"],
  ["relations_south_asia", "AFG BGD BTN IND LKA MDV NPL PAK"],
  ["relations_latam", "ARG BOL BRA CHL COL CRI CUB DOM ECU GTM HND HTI JAM NIC PAN PER PRY SLV TTO URY VEN BHS BRB BLZ GUY SUR MEX"],
  ["relations_africa", "AGO BDI BEN BFA BWA CAF CIV CMR COD COG COM CPV DJI ERI ETH GAB GHA GIN GMB GNB GNQ KEN LBR LSO MDG MLI MOZ MRT MUS MWI NAM NER NGA RWA SDN SEN SLE SOM SSD STP SWZ SYC TCD TGO TZA UGA ZAF ZMB ZWE"],
  ["relations_europe", "ALB AND AUT BEL BGR BIH BLR CHE CYP CZE DEU DNK ESP EST FIN FRA GBR GRC HRV HUN IRL ISL ITA LIE LTU LUX LVA MCO MDA MKD MLT MNE NLD NOR POL PRT ROU SRB SVK SVN SWE UKR XKX TUR ARM AZE GEO KAZ KGZ RUS TJK TKM UZB"],
  ["relations_mena", "ARE BHR DZA EGY IRN IRQ JOR KWT LBN LBY MAR OMN PSE QAT SAU SYR TUN YEM ISR USA CAN AUS NZL PNG FJI"],
];
const BY_ISO = new Map<string, string>(REGION_MEMBER.flatMap(([id, list]) => list.split(" ").map((c) => [c, id] as [string, string])));
/** The first ISO3 code in a free country field ("KEN", "KEN; UGA"); "" when it holds none we know. */
export const iso3In = (v: unknown): string => (String(v ?? "").toUpperCase().match(/\b[A-Z]{3}\b/g) || []).find((c) => BY_ISO.has(c)) || "";
/** The supplier-relations member whose region holds this country; null when the country is not known. */
export const regionMember = (country: string): Member | null => member(BY_ISO.get(iso3In(country)) || "");

export type Assignment = { lead: Member; support: Member[]; why: string };
/** Winner: the regional relations member writes to the winner, the tender analyst reads the contract. Tender: the
 *  analyst reads it and the sourcing lead builds the shortlist. Only members of lib/team.ts are ever named. */
export function assign(s: Signal): Assignment {
  const analyst = member("analyst")!, sourcing = member("sourcing")!;
  if (s.kind === "tender") return { lead: analyst, support: [sourcing], why: `${analyst.name} reads the tender, ${sourcing.name} builds the supplier shortlist` };
  const own = iso3In(s.winner_country), c = own || iso3In(s.country), rel = regionMember(c);
  if (!rel) return { lead: analyst, support: [], why: `no country on the award to pick a regional member: ${analyst.name} reads the contract` };
  return { lead: rel, support: [analyst], why: `${rel.name} writes to the winner (${own ? `winner country ${c}` : `winner country not stated, project country ${c}`}), ${analyst.name} reads the contract` };
}

// ---- score -------------------------------------------------------------------------------------------------
export type Scored = { score: number; reasons: string[]; skip: string };
const money = (n: number) => (n >= 1e9 ? `USD ${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `USD ${(n / 1e6).toFixed(1)}M` : `USD ${Math.round(n / 1e3)}K`);
const valuePoints = (v: number): [number, string] => (!(v > 0) ? [0, "no stated value: +0"] : v >= 50e6 ? [20, `value ${money(v)}: +20`] : v >= 10e6 ? [16, `value ${money(v)}: +16`] : v >= 1e6 ? [10, `value ${money(v)}: +10`] : v >= 1e5 ? [5, `value ${money(v)}: +5`] : [0, `value ${money(v)} (small): +0`]);
/** The focus words found in the signal's own text (title, needs, commodity, sector). */
export function focusHits(s: Signal, f: Focus): string[] {
  const hay = ` ${norm(`${s.title} ${(s.needs || []).join(" ")} ${s.commodity || ""} ${s.sector || ""}`)} `;
  return f.words.filter((w) => { const k = norm(w); return !!k && hay.includes(` ${k}`); });
}
export type ScoreOpts = { winnerDays: number; minDaysLeft: number };
/** Points with their reasons. skip: a reason this signal is not for the scouts at all (not a score matter). */
export function scoreSignal(s: Signal, f: Focus, now: number, o: ScoreOpts): Scored {
  const reasons: string[] = []; let score = 0;
  const add = (n: number, why: string) => { score += n; reasons.push(why); };
  const c = iso3In(s.country);
  if (c && f.excluded.includes(c)) return { score: 0, reasons: [`country ${c} is on the owner's excluded list`], skip: "skipped: excluded country" };
  const hits = focusHits(s, f);
  if (f.words.length && !hits.length) return { score: 0, reasons: [`none of the focus words (${f.words.slice(0, 8).join(", ")}) appear in the title, needs, commodity or sector`], skip: "skipped: outside focus" };
  if (hits.length) add(20, `fits the owner's focus (${hits.slice(0, 3).join(", ")}): +20`);
  if (c && f.partners.includes(c)) add(5, `partner country ${c}: +5`);
  const [vp, vwhy] = valuePoints(s.value_usd); add(vp, vwhy);
  if (s.kind === "winner") {
    const age = ageDays(s.date, now);
    if (!Number.isFinite(age)) return { score: 0, reasons: ["the award has no readable date, so it cannot be called fresh"], skip: "skipped: no date" };
    if (age > o.winnerDays) return { score: 0, reasons: [`awarded ${age} days ago, older than the ${o.winnerDays}-day window`], skip: "skipped: not fresh" };
    add(Math.max(0, 30 - age), `awarded ${age} day${age === 1 ? "" : "s"} ago (${s.date}): +${Math.max(0, 30 - age)}`);
    const wc = iso3In(s.winner_country);
    if (wc && c && wc !== c) add(10, `foreign winner (${wc} on a ${c} contract), imports anyway: +10`);
    else if (wc) reasons.push(`winner from the project country (${wc}): +0`);
    else reasons.push("winner country not stated: +0");
    if (s.winner_kind === "commodity") add(5, `commodity contract${s.commodity ? ` (${s.commodity})` : ""}, the winner has to source it now: +5`);
    if (s.contact || s.website) add(10, `${s.contact ? "published commercial contact" : "company website"} on record: +10`);
    else reasons.push("no published contact on record: +0");
    if (s.buyer_awards != null) { if (s.buyer_awards >= 5) add(5, `buyer has ${s.buyer_awards} awards in the award data: +5`); else reasons.push(`buyer has ${s.buyer_awards} awards in the award data: +0`); }
  } else {
    const dl = s.days_left;
    if (dl != null && Number.isFinite(dl) && dl < o.minDaysLeft) return { score: 0, reasons: [`deadline in ${dl} days, under the ${o.minDaysLeft}-day minimum to build a bid`], skip: "skipped: deadline too close" };
    if (/set-aside/i.test(s.access || "")) return { score: 0, reasons: ["reserved for local bidders (set-aside)"], skip: "skipped: reserved for local bidders" };
    add(10, "first seen in the last 2 days (the index marks it new): +10");
    if (s.fit != null && Number.isFinite(s.fit)) { const p = Math.round(Math.max(0, Math.min(100, s.fit)) * 0.3); add(p, `system deal fit ${Math.round(s.fit)}: +${p}`); }
    else reasons.push("no deal fit computed: +0");
    if (dl != null && Number.isFinite(dl)) add(dl >= 21 ? 10 : 5, `deadline in ${dl} days: +${dl >= 21 ? 10 : 5}`); else reasons.push("no stated deadline: +0");
    // the tender store has no works/goods/services column; a named commodity is the goods signal it does carry
    if (/goods|supply|supplies/i.test(s.nature || "")) add(10, `nature of the tender is goods (${s.nature}): +10`);
    else if (s.commodity) add(10, `names a commodity (${s.commodity}), a goods purchase: +10`);
    else reasons.push("no goods marker on the notice: +0");
    if (/^international|world bank|\(icb\)|\bicb\b|^global tender/i.test(s.access || "")) add(10, "open to foreign bidders by rule: +10");
    if (/^pursue$/i.test(s.decision || "")) add(5, "the system's decision is Pursue: +5");
    if (s.buyer_awards != null && s.buyer_awards > 0) add(5, `buyer made ${s.buyer_awards} awards in 12 months: +5`);
  }
  return { score: Math.min(100, score), reasons, skip: "" };
}

// ---- briefs ------------------------------------------------------------------------------------------------
const who = (m: Member) => `${m.name} (${m.title})`;
/** The instruction a scout run starts from. The first line is short: it becomes the title of the deal. */
export function briefFor(s: Signal, a: Assignment, reasons: string[], maxTurns: number): string {
  const tail = `\nThis run was opened by a scout, not by a request from the owner. He has not seen this lead yet. Do not use ask_owner: when a fact is missing, say so in the final report. You have at most ${maxTurns} steps, so plan to finish inside them and keep the last one for finish. Nothing is sent by you: propose_message only prepares the message for his Approve or Reject button.
End with finish, written for the owner: 1) what was found, with the sources; 2) why it is worth his time (and say so plainly if it is not); 3) what is proposed and what waits for his approval; 4) what is missing.
Why the scout picked it: ${reasons.join("; ")}.`;
  if (s.kind === "winner") {
    const val = s.value_usd > 0 ? `, ${money(s.value_usd)}` : "";
    return `Scout lead, contract winner: ${cut(s.winner, 80)} won "${cut(s.title, 140)}" from ${cut(s.buyer, 80) || "an unnamed buyer"} (${s.country || "country not stated"}${val}).
Award date ${s.date || "unknown"}, source ${s.source || "the award index"}${s.link ? `, ${s.link}` : ""}. Winner country: ${s.winner_country || "not stated"}. Needs inferred by the index from the contract title: ${(s.needs || []).join(", ") || "none listed"}. On record: website ${s.website || "none"}, published contact ${s.contact || "none"}${s.contact_page ? ` (from ${s.contact_page})` : ""}.
Team: ${who(a.lead)} leads${a.support.length ? `, with ${a.support.map(who).join(" and ")}` : ""}.
Do this: 1) confirm what ${cut(s.winner, 80)} does from its own website (web search) and check its record with company_footprint; 2) infer what it must buy for this contract and say plainly that this is inferred from the contract title, not confirmed; 3) match one or two of those needs to suppliers from the index (search_suppliers) with a price basis, and say what the basis is; 4) save the winner as a party of the deal (record, kind party, role buyer) with its published commercial contact and the page it comes from: business contact details only, never a private person's; 5) propose_message a short first note to that contact, written by ${a.lead.name}: congratulations on the named contract, the one or two items we can supply and from where, and a question about their procurement timeline. No price and no claim that we know their needs.${tail}`;
  }
  const val = s.value_usd > 0 ? `, estimated ${money(s.value_usd)}` : "";
  return `Scout lead, new tender ${s.id}: "${cut(s.title, 140)}" by ${cut(s.buyer, 80) || "an unnamed buyer"} (${s.country || "country not stated"}${val}).
Deadline in ${s.days_left ?? "an unknown number of"} days. Access: ${s.access || "not stated"}. Commodity: ${s.commodity || "not named"}. Sector: ${s.sector || "not stated"}.${s.link ? ` Notice: ${s.link}.` : ""}
Team: ${who(a.lead)} leads${a.support.length ? `, with ${a.support.map(who).join(" and ")}` : ""}.
Do this: 1) the entry route (tender_routes on ${s.id}) and who may bid: state each eligibility condition and whether it is met, not met or unknown; 2) the goods to source, as specific as the notice allows; 3) a shortlist of suppliers from the index for the exact product (search_suppliers, makers first), with their contacts; 4) an outline of the economics (deal_economics) when there is a price basis, with every assumption labelled, or say that there is no basis yet; 5) propose_message one request for quotation to the best supplier, written by the supplier-relations member of that supplier's region.${tail}`;
}

// ---- the chooser -------------------------------------------------------------------------------------------
export type Limits = {
  /** runs the scouts may start per UTC day, and how many they already started today */
  maxRunsPerDay: number; runsToday: number;
  /** runs one round (one cron call) may start */
  maxRunsPerRound: number;
  /** runs the daily AI budget still has room for (Infinity when no budget line is set) */
  budgetRuns: number;
  /** a signal under this score is not worth a run */
  minScore: number;
  /** how many unseen signals one round looks at, best first: each of them gets a recorded decision */
  look: number;
  maxTurns: number;
} & ScoreOpts;
export type Pick = { signal: Signal; score: number; reasons: string[]; assignee: Member; support: Member[]; brief: string; decision: string; label: string };
export const labelOf = (s: Signal) => (s.kind === "winner" ? `${cut(s.winner, 70)}: ${cut(s.title, 110)}` : cut(s.title, 180));

/** Which signals are pursued now, and what happens to the rest of the ones looked at. A signal with a final decision on
 *  record (pursued, or skipped for a reason about the signal itself) is never looked at again; one that was held back by
 *  a limit is. Pure: the same inputs give the same answer. */
export function choose(candidates: Signal[], seen: SeenRow[], ws: string, focus: Focus, lim: Limits, now: number): { chosen: Pick[]; skipped: Pick[]; room: number; held_by: string } {
  const last = latestSeen(seen, ws);
  const ids = new Set<string>();
  const fresh = candidates.filter((s) => {
    const k = keyOf(s.kind, s.id), prev = last.get(k);
    if (!s.id || ids.has(k) || (prev && !transient(prev.decision))) return false;
    ids.add(k); return true;
  });
  const scored = fresh.map((signal) => ({ signal, ...scoreSignal(signal, focus, now, lim) }))
    .sort((a, b) => Number(!!a.skip) - Number(!!b.skip) || b.score - a.score || b.signal.value_usd - a.signal.value_usd || (a.signal.id < b.signal.id ? -1 : 1));  // equal scores: the larger contract first
  const left = Math.max(0, lim.maxRunsPerDay - lim.runsToday);
  const room = Math.max(0, Math.min(left, lim.maxRunsPerRound, lim.budgetRuns));
  const held_by = room > 0 ? "" : left <= 0 ? `daily run limit reached (${lim.maxRunsPerDay} a day)` : lim.budgetRuns <= 0 ? "no room left in today's AI budget" : "round limit";
  const chosen: Pick[] = [], skipped: Pick[] = [];
  for (const x of scored.slice(0, Math.max(1, lim.look))) {
    const a = assign(x.signal);
    const base = { signal: x.signal, score: x.score, assignee: a.lead, support: a.support, label: labelOf(x.signal) };
    if (x.skip) { skipped.push({ ...base, reasons: x.reasons, brief: "", decision: x.skip }); continue; }
    const reasons = [...x.reasons, a.why];
    if (x.score < lim.minScore) { skipped.push({ ...base, reasons: [`score ${x.score} is under the minimum ${lim.minScore}`, ...reasons], brief: "", decision: "skipped: low score" }); continue; }
    if (chosen.length >= room) {
      const why = held_by || (left <= chosen.length ? `daily run limit reached (${lim.maxRunsPerDay} a day)` : lim.budgetRuns <= chosen.length ? "no room left in today's AI budget" : `one round starts at most ${lim.maxRunsPerRound}`);
      skipped.push({ ...base, reasons: [why, ...reasons], brief: "", decision: LIMIT }); continue;
    }
    chosen.push({ ...base, reasons, brief: briefFor(x.signal, a, x.reasons, lim.maxTurns), decision: PURSUED });
  }
  return { chosen, skipped, room, held_by };
}
