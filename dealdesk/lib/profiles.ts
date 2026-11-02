import { appendRow, ENGINE_SHEET, readRanges, writeRange } from "./sheets";

// One profile per user: what they sell or buy, where, deal size, lens and digest settings.
// Stored in the 'Profiles' tab (A email, B updated, C JSON). Behind this module so the move to a database touches
// only this file.
export type Lens = "maker" | "trader" | "foreign" | "consultant" | "institution";
export type Profile = {
  lens: Lens;
  sectors: string[];          // tender sectors (the index's "s" values)
  groups: string[];           // commodity groups
  keywords: string[];         // free words matched in titles
  regions: string[];
  countries: string[];        // ISO3
  partners: string[];         // ISO3 where the user has a local partner
  excluded: string[];         // ISO3 never shown (default for Israeli users: countries that bar Israeli firms)
  valueMin: number | null;    // USD
  valueMax: number | null;
  mode: "focus" | "broad";
  digest: "daily" | "weekly" | "off";
  minScore: number;           // focus threshold and alert threshold
  lang: "he" | "en";
  hidden: string[];           // items marked not relevant (ids), newest last
  saved: string[];            // watchlist (ids)
  lastDigest?: string;
  sent?: string[];            // ids already sent in a digest, newest last
};

export const DEFAULT_EXCLUDED = ["IRN", "SYR", "LBN", "YEM", "IRQ"];
export const LENSES: Lens[] = ["maker", "trader", "foreign", "consultant", "institution"];
const TAB = "Profiles";
const strs = (v: unknown, max = 60, len = 120) =>
  (Array.isArray(v) ? v : []).map((x) => String(x ?? "").trim().slice(0, len)).filter(Boolean).slice(0, max);
const num = (v: unknown) => (v === null || v === "" || v === undefined || !isFinite(Number(v)) ? null : Math.max(0, Number(v)));

export function cleanProfile(p: Partial<Profile> & Record<string, unknown>, prev?: Profile | null): Profile {
  return {
    lens: LENSES.includes(p.lens as Lens) ? (p.lens as Lens) : prev?.lens || "maker",
    sectors: strs(p.sectors),
    groups: strs(p.groups),
    keywords: strs(p.keywords, 30, 40).map((k) => k.toLowerCase()),
    regions: strs(p.regions, 20),
    countries: strs(p.countries, 80, 3).map((c) => c.toUpperCase()).filter((c) => /^[A-Z]{3}$/.test(c)),
    partners: strs(p.partners, 80, 3).map((c) => c.toUpperCase()).filter((c) => /^[A-Z]{3}$/.test(c)),
    excluded: (Array.isArray(p.excluded) ? strs(p.excluded, 80, 3) : prev?.excluded ?? (p.lens === "foreign" ? [] : DEFAULT_EXCLUDED))
      .map((c) => c.toUpperCase()).filter((c) => /^[A-Z]{3}$/.test(c)),
    valueMin: num(p.valueMin),
    valueMax: num(p.valueMax),
    mode: p.mode === "broad" ? "broad" : "focus",
    digest: p.digest === "weekly" || p.digest === "off" ? p.digest : "daily",
    minScore: Math.min(95, Math.max(30, Number(p.minScore) || 60)),
    lang: p.lang === "en" ? "en" : "he",
    hidden: strs(p.hidden ?? prev?.hidden, 2000, 120),
    saved: strs(p.saved ?? prev?.saved, 500, 120),
    lastDigest: String(p.lastDigest ?? prev?.lastDigest ?? ""),
    sent: strs(p.sent ?? prev?.sent, 3000, 120),
  };
}

let cache: { at: number; rows: { row: number; email: string; p: Profile }[] } | null = null;

async function all(fresh = false) {
  if (!fresh && cache && Date.now() - cache.at < 30_000) return cache.rows;
  const v = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:C2000`]).catch(() => null))?.[0] || [];
  const rows: { row: number; email: string; p: Profile }[] = [];
  v.forEach((r, i) => {
    const email = String(r[0] || "").trim().toLowerCase();
    if (!email) return;
    try { rows.push({ row: i + 2, email, p: cleanProfile(JSON.parse(String(r[2] || "{}"))) }); } catch { /* skip a broken row */ }
  });
  cache = { at: Date.now(), rows };
  return rows;
}

export async function getProfile(email: string): Promise<Profile | null> {
  const e = email.trim().toLowerCase();
  return (await all()).find((r) => r.email === e)?.p || null;
}

export async function allProfiles(): Promise<{ email: string; p: Profile }[]> {
  return (await all(true)).map(({ email, p }) => ({ email, p }));
}

export async function saveProfile(email: string, p: Profile): Promise<void> {
  const e = email.trim().toLowerCase();
  const now = new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 16);
  const hit = (await all(true)).find((r) => r.email === e);
  const json = JSON.stringify(p);
  if (json.length > 45000) throw new Error("profile too large");
  if (hit) await writeRange(`'${TAB}'!A${hit.row}:C${hit.row}`, [[e, now, json]]);
  else await appendRow(TAB, [e, now, json]);
  cache = null;
}
