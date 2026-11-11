// Comparable public awards (corpus A of the F11 specification). Descriptive only: which public awards look like this
// query, who won them, how large they were. This is public award history, not Sinder outcomes. It gives no score,
// no ranking of chances and no forecast. Pure module: the caller passes the rows and the point in time.

/** One public award row, with the field names of the award feed read by leads/footprints.py. */
export type AwardRow = {
  published: string;                 // YYYY-MM-DD (a longer ISO time is accepted)
  title: string;
  value_usd?: number | string | null;
  value?: number | string | null;    // used only when currency is USD and value_usd is absent (same rule as footprints.py)
  currency?: string | null;
  country: string;                   // ISO3 of the project
  buyer: string;
  winners: string[] | string;        // a list, or names separated by ";"
  winner_country?: string | null;
  id?: string; source?: string; url?: string;
};
export type ComparableQuery = { words?: string | string[]; country?: string; buyer?: string; from?: string; to?: string };
export type ComparableAward = { published: string; title: string; value_usd: number | null; country: string; buyer: string; winners: string[];
  id?: string; source?: string; url?: string; why: string[]; notices: number };
export type Comparables = {
  kind: "public_award_history";
  statement: string;
  as_of: string;
  n: number;
  rows: ComparableAward[];
  by_year: Record<string, number>;
  by_winner: { name: string; awards: number }[];
  value_usd: { n: number; min: number | null; median: number | null; max: number | null; note: string };
  excluded: { published_after_as_of: number; undated: number; duplicate_notices: number };
};
export const STATEMENT = "public award history, not Sinder outcomes";
export const MIN_N_FOR_MEDIAN = 5;

// Same name normalisation as lib/index.ts fpNorm and leads/footprints.py norm (kept local so this module stays free of I/O imports).
const STOP = new Set(["co", "ltd", "limited", "llc", "inc", "plc", "sa", "sas", "srl", "spa", "gmbh", "ag", "bv", "pvt", "private", "the", "and", "of", "corp",
  "corporation", "company", "sdn", "bhd", "pte", "jsc", "ojsc", "pjsc", "cjsc", "pty", "sarl", "ltda", "cia", "sac", "eirl", "llp", "lp", "nv", "oy", "ab", "as"]);
export const nameNorm = (s: string) => (String(s || "").toLowerCase().match(/[a-z0-9]+/g) || []).filter((x) => !STOP.has(x) && x.length > 1).join(" ").slice(0, 80);
const titleNorm = (s: string) => (String(s || "").toLowerCase().match(/[\p{L}\p{N}]+/gu) || []).join(" ");
const dayMs = (s: unknown): number => { const d = typeof s === "string" && /^\d{4}-\d{2}-\d{2}/.test(s) ? Date.parse(s.slice(0, 10)) : NaN; return d; };
const winnersOf = (w: AwardRow["winners"]) => (Array.isArray(w) ? w : String(w || "").split(";")).map((x) => String(x).trim()).filter(Boolean);
function usdOf(r: AwardRow): number | null {
  let v = Number(r.value_usd || 0);
  if (!v && String(r.currency || "USD").toUpperCase() === "USD") v = Number(r.value || 0);
  return Number.isFinite(v) && v > 0 && v < 5e9 ? v : null;   // same sanity bounds as footprints.py; no currency conversion here
}
/** Two notices of one award share this key: same buyer, same normalised title, same publication date. */
export const awardKey = (r: Pick<AwardRow, "buyer" | "title" | "published">) => `${nameNorm(r.buyer)}|${titleNorm(r.title)}|${String(r.published || "").slice(0, 10)}`;

export function comparableAwards(query: ComparableQuery, rows: AwardRow[], asOf: string): Comparables {
  const lim = Date.parse(asOf);
  if (typeof asOf !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(asOf) || Number.isNaN(lim)) throw new Error(`asOf is not a readable ISO time: ${JSON.stringify(asOf)}`);
  const words = (Array.isArray(query.words) ? query.words : String(query.words || "").split(/[\s,]+/)).map((w) => titleNorm(w)).filter((w) => w.length > 1);
  const country = String(query.country || "").trim().toUpperCase();
  const buyerWords = nameNorm(query.buyer || "").split(" ").filter(Boolean);
  const from = query.from ? dayMs(query.from) : null, to = query.to ? dayMs(query.to) : null;
  if ((query.from && Number.isNaN(from)) || (query.to && Number.isNaN(to))) throw new Error("period dates must be YYYY-MM-DD");
  if (!words.length && !country && !buyerWords.length && from === null && to === null) throw new Error("a comparable query needs at least one of: words, country, buyer, period");

  const excluded = { published_after_as_of: 0, undated: 0, duplicate_notices: 0 };
  const seen = new Map<string, ComparableAward>();
  for (const r of rows) {
    const d = dayMs(r.published);
    if (Number.isNaN(d)) { excluded.undated++; continue; }             // without a date nothing proves it was known at asOf
    if (d > lim) { excluded.published_after_as_of++; continue; }
    const why: string[] = [];
    if (words.length) {
      const t = ` ${titleNorm(r.title)} `;
      if (!words.every((w) => t.includes(w))) continue;
      why.push(`title contains ${words.map((w) => `"${w}"`).join(", ")}`);
    }
    if (country) { if (String(r.country || "").toUpperCase() !== country) continue; why.push(`country ${country}`); }
    if (buyerWords.length) {
      const b = nameNorm(r.buyer).split(" ");
      if (!buyerWords.every((w) => b.includes(w))) continue;
      why.push(`buyer name contains ${buyerWords.map((w) => `"${w}"`).join(", ")}`);
    }
    if (from !== null || to !== null) {
      if ((from !== null && d < from) || (to !== null && d > to)) continue;
      why.push(`published ${query.from || "any"} to ${query.to || "any"}`);
    }
    const k = awardKey(r), prev = seen.get(k), usd = usdOf(r), win = winnersOf(r.winners);
    if (prev) {   // a second notice of the same award: one award, keep whatever the first notice lacked
      excluded.duplicate_notices++; prev.notices++;
      if (prev.value_usd === null) prev.value_usd = usd;
      for (const w of win) if (!prev.winners.some((x) => nameNorm(x) === nameNorm(w))) prev.winners.push(w);
      continue;
    }
    seen.set(k, { published: String(r.published).slice(0, 10), title: r.title, value_usd: usd, country: String(r.country || "").toUpperCase(), buyer: r.buyer,
      winners: win, id: r.id, source: r.source, url: r.url, why, notices: 1 });
  }
  const out = [...seen.values()].sort((a, b) => (a.published < b.published ? 1 : a.published > b.published ? -1 : 0));
  const by_year: Record<string, number> = {};
  const wins = new Map<string, { name: string; awards: number }>();
  for (const a of out) {
    by_year[a.published.slice(0, 4)] = (by_year[a.published.slice(0, 4)] || 0) + 1;
    for (const k of new Set(a.winners.map(nameNorm).filter(Boolean))) {
      const cur = wins.get(k) || { name: a.winners.find((w) => nameNorm(w) === k) as string, awards: 0 };
      cur.awards++; wins.set(k, cur);
    }
  }
  const vals = out.map((a) => a.value_usd).filter((v): v is number => v !== null).sort((a, b) => a - b);
  const enough = out.length >= MIN_N_FOR_MEDIAN && vals.length >= MIN_N_FOR_MEDIAN;
  const median = enough ? (vals.length % 2 ? vals[(vals.length - 1) / 2] : (vals[vals.length / 2 - 1] + vals[vals.length / 2]) / 2) : null;
  return {
    kind: "public_award_history", statement: STATEMENT, as_of: asOf, n: out.length, rows: out,
    by_year: Object.fromEntries(Object.entries(by_year).sort()),
    by_winner: [...wins.values()].sort((a, b) => b.awards - a.awards || a.name.localeCompare(b.name)),
    value_usd: { n: vals.length, min: vals.length ? vals[0] : null, median, max: vals.length ? vals[vals.length - 1] : null,
      note: enough ? `median of ${vals.length} awards with a stated value` : `fewer than ${MIN_N_FOR_MEDIAN} awards with a stated value: no median is given` },
    excluded,
  };
}
