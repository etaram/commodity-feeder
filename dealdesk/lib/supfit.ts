import type { Supplier } from "@/lib/index";

// What a supplier is to Sinder, fixed at load time (mirrors leads/universe.py so an index built before the rule
// gets the same treatment; a row the builder already corrected carries qv >= 2 and is left alone).
// - Identity beats the contract mix: a company whose name or own site says defence, laundry or cleaning is that.
// - Sinder buys goods across borders. A company that only delivers services on site (laundry, cleaning, catering,
//   maintenance, consulting, engineering design, training) is not a supplier for it, however much it won, so its
//   quality is scaled down and it ranks after the goods suppliers of its tier.
export const DEFENCE_ID = /\b(defen[cs]e|military|armament|arms|ammunition|munitions|missiles?|ordnance|leonardo|rafael|elbit|thales|rheinmetall|saab|bae systems|kongsberg|nexter|knds|krauss-?maffei|hensoldt|aselsan|roketsan|mbda|lockheed|raytheon|northrop|general dynamics|iveco defence|patria|nammo|fn herstal|colt|beretta|glock|sig sauer)\b/i;
export const CLEANING_ID = /\b(laundry|laundries|linen|textile (rental|service)|workwear rental|vask\w*|w[äa]scherei|blanchisserie|lavander[ií]a|wasserij|tv[äa]tteri|pesula|pralnia|cleaning|rengøring|reinigung|nettoyage|limpieza|schoonmaak|st[äa]d\w*|facility services|facility management|catering|canteen)\b/i;
export const SERVICE_SECTOR = new Set(["Repair, maintenance & installation", "Transport & logistics services", "Engineering & architecture services",
  "Consulting, business & financial services", "Environment, waste & cleaning", "Education, social & hospitality services"]);
const GOODS_HINT = /\b(manufactur\w*|producers?|factory|mill|supplier of|supplies of|equipment|machinery|vehicles|parts|spare|products?)\b/i;

export function isServiceOnly(s: Supplier): boolean {
  const ty = String(s.ty || "");
  if (/goods supplier|manufactur|producer/i.test(ty) || s.td === "yes") return false;
  if (s.hs || s.sh) return false; // customs exports are goods
  if (CLEANING_ID.test(`${s.n || ""} ${s.wt || ""} ${s.in || ""}`)) return true;
  return SERVICE_SECTOR.has(String(s.s || "")) && (/services/i.test(ty) || !GOODS_HINT.test(`${s.p || ""} ${s.sp || ""}`));
}

export function normalizeSuppliers(rows: Supplier[]) {
  for (const s of rows as (Supplier & { qv?: number; _n?: 1 })[]) {
    if (s._n || (s.qv || 0) >= 2) continue;
    s._n = 1;
    const idText = `${s.n || ""} ${s.in || ""}`, siteText = `${s.n || ""} ${s.wt || ""} ${s.in || ""}`;
    const setMain = (sec: string) => { if (s.s === sec) return; const rest = [s.s, ...String(s.s2 || "").split(/;\s*/)].filter((x) => x && x !== sec); s.s = sec; s.s2 = rest.slice(0, 2).join("; "); };
    if (DEFENCE_ID.test(idText)) setMain("Defence & security");
    else if (CLEANING_ID.test(siteText)) setMain("Environment, waste & cleaning");
    if (isServiceOnly(s)) { s.q = Math.round((Number(s.q) || 0) * 0.6); if (!/services/i.test(String(s.ty || ""))) s.ty = "works/services"; }
  }
  return rows;
}
