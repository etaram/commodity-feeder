// Screening of a company name against the official sanctions lists (OFAC, UN Security Council, EU), indexed daily by
// the sanctions workflow into data/leads/sanctions.json. Name matching only: a hit is a lead to verify, never a verdict.
type Ent = [string[], string, string, string, string];
let mem: { at: number; updated: string; ents: Ent[]; toks: string[][][] } | null = null;

const STOP = new Set(["ltd", "limited", "llc", "inc", "incorporated", "co", "company", "corp", "corporation", "gmbh", "sa", "sarl", "ag", "bv", "nv", "plc", "jsc", "ojsc", "pjsc", "ooo", "zao", "oao", "llp", "lp", "pte", "pvt", "private", "public", "the", "of", "and", "for", "international", "group", "holding", "holdings", "trading", "general", "services", "industries", "industrial", "enterprises", "enterprise", "ab", "as", "oy", "spa", "srl", "kg", "ltda", "fze", "fzc", "fzco", "lc"]);
export const norm = (s: string) => s.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9Ѐ-ӿ֐-׿؀-ۿ一-鿿 ]+/g, " ").replace(/\s+/g, " ").trim();
const toks = (s: string) => norm(s).split(" ").filter((t) => t && !STOP.has(t));

async function load() {
  if (mem && Date.now() - mem.at < 6 * 3600_000) return mem;
  const r = await fetch("https://raw.githubusercontent.com/etaram/commodity-feeder/main/data/leads/sanctions.json", { cache: "no-store", signal: AbortSignal.timeout(20000) });
  if (!r.ok) throw new Error("sanctions index HTTP " + r.status);
  const j = await r.json();
  const ents: Ent[] = j.e || [];
  mem = { at: Date.now(), updated: j.updated || "", ents, toks: ents.map((e) => e[0].map(toks)) };
  return mem;
}

export async function sanctionsFacts(name: string): Promise<string> {
  const q = toks(name);
  if (!q.length) return "";
  const m = await load();
  const qs = new Set(q), qn = q.join(" ");
  const hits: { strength: number; line: string }[] = [];
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
    if (best) hits.push({ strength: best, line: `- ${best === 3 ? "STRONG name match" : best === 2 ? "Close name match" : "Partial name match"}: "${via}" on ${e[1]} (${e[3]}${e[2] ? ", program " + e[2] : ""}, ref ${e[4]})` });
  });
  hits.sort((a, b) => b.strength - a.strength);
  const head = `Sanctions screening (OFAC SDN and consolidated, UN Security Council, EU and UK consolidated; index updated ${m.updated} UTC; name matching only, verify identity, address and registration number before concluding):`;
  return hits.length ? [head, ...hits.slice(0, 6).map((h) => h.line)].join("\n") : `${head}\n- No name match found for "${name}" in those lists. This does not cover the Swiss, Canadian or Israeli lists, nor aliases not published.`;
}
