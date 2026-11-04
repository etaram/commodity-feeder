import { ENGINE_SHEET, readRanges } from "./sheets";

// "Who do I know there": the owner's own contacts (private tab 'My Network' in the engine sheet, pasted from a
// LinkedIn connections export or typed: First Name, Last Name, Company, Position, Email, Country, Note).
// Matched by company name tokens against buyers, winners and suppliers; the names never leave the server
// except as "you know X (title) at Y" on a record the signed-in user is looking at.
const TAB = "My Network";
const STOP = new Set(["ltd", "limited", "inc", "co", "corp", "corporation", "company", "group", "plc", "sa", "ag", "gmbh", "llc", "the", "of", "and", "de", "spa", "srl", "bv", "nv", "as", "ab", "oy", "international", "holdings", "holding", "services", "solutions", "industries", "industrial", "engineering", "construction", "technologies", "technology", "global", "national", "ministry", "government", "authority", "agency", "department", "public", "general"]);
const tokens = (s: string) => new Set(String(s || "").toLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").split(" ").filter((w) => w.length > 2 && !STOP.has(w)));
type Person = { name: string; company: string; title: string; country: string; note: string; tok: Set<string> };
let cache: { at: number; people: Person[] } | null = null;

async function people(): Promise<Person[]> {
  if (cache && Date.now() - cache.at < 300_000) return cache.people;
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:G5000`]).catch(() => null))?.[0] || [];
  const out: Person[] = [];
  for (const r of rows) {
    if (!r || !(r[2] || "").trim()) continue;
    out.push({ name: `${r[0] || ""} ${r[1] || ""}`.trim(), company: r[2] || "", title: r[3] || "", country: r[5] || "", note: r[6] || "", tok: tokens(r[2]) });
  }
  cache = { at: Date.now(), people: out };
  return out;
}

// For each organisation name, the contacts whose company shares at least two distinctive tokens (or the only token).
export async function whoIKnow(names: string[]): Promise<Record<string, { name: string; title: string; company: string }[]>> {
  const ps = await people();
  const out: Record<string, { name: string; title: string; company: string }[]> = {};
  if (!ps.length) return out;
  for (const n of names.slice(0, 20)) {
    const t = tokens(n);
    if (!t.size) continue;
    const hits = ps.filter((p) => { let k = 0; for (const w of p.tok) if (t.has(w)) k++; return k >= Math.min(2, p.tok.size) && k >= 1; }).slice(0, 5);
    if (hits.length) out[n] = hits.map((p) => ({ name: p.name, title: p.title, company: p.company }));
  }
  return out;
}
