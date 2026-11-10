import TAX from "@/lib/commodities.json";

// Commodity layer of the supplier search (code only, no model call). A request that names a traded commodity
// ("sidamo coffee producer", "jasmine rice", "אורז יסמין") is read against lib/commodities.json: the commodity's
// trade terms and customs headings, its varieties with their origin countries, and the look-alike phrases that are
// not the commodity ("coffee table", "rice cooker"). leads/describe.py reads the same file, so the tags stored on a
// supplier and the search agree.
type Var = { a: string[]; o: string[] };
type Entry = { key: string; terms: string[]; hs: string[]; origins: string[]; not: string; varieties: Record<string, Var>; he: string[] };
const LIST = (TAX as unknown as { commodities: Entry[] }).commodities;
const HE_VAR: Record<string, string> = { "סידמו": "sidamo", "סידאמו": "sidamo", "ירגשף": "yirgacheffe", "ירגצ'ף": "yirgacheffe", "יסמין": "jasmine", "בסמטי": "basmati", "רובוסטה": "robusta", "ערביקה": "arabica", "הומרה": "humera" };
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const wordRe = (alts: string[], flags = "i") => new RegExp(`(?:^|[^\\p{L}\\p{N}])(?:${alts.map(esc).join("|")})s?(?![\\p{L}\\p{N}])`, flags + "u");

export type Commodity = {
  key: string; hs: string[]; origins: string[];
  term: RegExp;                 // the commodity itself, in a text already cleaned of look-alikes
  clean: (text: string) => string;   // removes the look-alike phrases ("coffee table") from a text
  variety?: { name: string; re: RegExp; origins: string[] };
  rest: string[];               // other words of the request (preferences, e.g. "organic", "washed")
};
const ROLE = /^(producers?|manufacturers?|makers?|exporters?|suppliers?|sellers?|growers?|farmers?|traders?|company|companies|origin|from|of|the|and|for|in|buy|wholesale|bulk|green|raw|beans?|seeds?|grains?)$/;

export function detectCommodity(raw: string): Commodity | null {
  let q = ` ${String(raw || "").toLowerCase().replace(/\s+/g, " ").trim()} `;
  if (q.length < 4 || q.length > 90) return null;
  for (const [he, en] of Object.entries(HE_VAR)) if (q.includes(he)) q = q.replace(he, ` ${en} `);
  let best: { e: Entry; len: number } | null = null;
  for (const e of LIST) {
    if (e.not && new RegExp(e.not, "i").test(q)) continue;   // the request itself is the look-alike ("coffee machine")
    const names = [...e.terms, ...Object.values(e.varieties).flatMap((v) => v.a)];
    let len = 0;
    for (const t of names) if (t.length > len && wordRe([t]).test(q)) len = t.length;
    for (const h of e.he) if (h.length > len && q.includes(h)) len = h.length;
    if (len && (!best || len > best.len)) best = { e, len };
  }
  if (!best) return null;
  const e = best.e;
  const notRe = e.not ? new RegExp(e.not, "giu") : null;
  let variety: Commodity["variety"];
  for (const [name, v] of Object.entries(e.varieties)) if (wordRe(v.a).test(q)) { variety = { name, re: wordRe(v.a), origins: v.o }; break; }
  const used = new Set([...e.terms, ...(variety ? e.varieties[variety.name].a : [])].flatMap((t) => t.split(" ")));
  const rest = q.replace(/[^\p{L}\p{N} ]/gu, " ").split(" ").filter((w) => w.length >= 3 && !/[֐-׿]/.test(w) && !ROLE.test(w) && !used.has(w) && !used.has(w.replace(/s$/, "")));
  return { key: e.key, hs: e.hs, origins: e.origins, term: wordRe(e.terms),
    clean: (t: string) => (notRe ? t.replace(notRe, " ") : t), variety, rest: [...new Set(rest)].slice(0, 5) };
}
