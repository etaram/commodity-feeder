import { logEvent } from "@/lib/log";
import { sanctionsFacts, norm } from "@/lib/sanctions";
// Verified registry checks for the business-intelligence report. Official open data only.
// Israel: data.gov.il (Registrar of Companies, Official Receiver liquidation file).
// UK: Companies House API, only if COMPANIES_HOUSE_KEY is set (free key from Companies House).
const CKAN = "https://data.gov.il/api/3/action/datastore_search";
const ICA = "f004176c-b85f-4542-8901-7b3176f9a054";
const LIQ = "d8715392-287f-49b7-9ae3-f21ec5bf55f3";

async function j(url: string, init?: RequestInit): Promise<any> {
  const r = await fetch(url, { ...init, signal: AbortSignal.timeout(12000), cache: "no-store" });
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}
const ckan = (rid: string, p: Record<string, string>) =>
  j(`${CKAN}?resource_id=${rid}&limit=5&` + new URLSearchParams(p).toString());

async function israel(name: string, legalId: string): Promise<string[]> {
  const out: string[] = [];
  const id = String(legalId || "").replace(/\D/g, "");
  let recs: any[] = [];
  if (id.length >= 8) recs = (await ckan(ICA, { filters: JSON.stringify({ "מספר חברה": Number(id) }) })).result.records;
  if (!recs.length && name) recs = (await ckan(ICA, { q: name.replace(/\b(ltd|limited|inc)\b\.?/gi, "").trim() })).result.records;
  if (!recs.length) return ["Israeli Registrar of Companies (data.gov.il): no matching company found by " + (id ? "number or " : "") + "name."];
  const exact = id ? recs.filter((r) => String(r["מספר חברה"]) === id) : [];
  const use = exact.length ? exact : recs.slice(0, 3);
  out.push(`Israeli Registrar of Companies (data.gov.il)${exact.length ? "" : ", matched by name only, verify it is the same company"}:`);
  for (const r of use) {
    const num = r["מספר חברה"];
    out.push(`- ${r["שם באנגלית"] || r["שם חברה"]} (${r["שם חברה"]}), no. ${num}: status ${r["סטטוס חברה"]}${r["תת סטטוס"] ? " / " + r["תת סטטוס"] : ""}; type ${r["סוג תאגיד"]}; incorporated ${r["תאריך התאגדות"]}; government company: ${r["חברה ממשלתית"]}; violating-company flag: ${r["מפרה"] ? r["מפרה"] : "none"}; last annual report filed: ${r["שנה אחרונה של דוח שנתי (שהוגש)"] || "unknown"}; address ${[r["שם רחוב"], r["מספר בית"], r["שם עיר"]].filter(Boolean).join(" ")}.`);
    try {
      const l = (await ckan(LIQ, { filters: JSON.stringify({ "מספר זיהוי של החברה": Number(num) }) })).result.records;
      out.push(l.length ? "  Official Receiver liquidation file: " + l.map((x: any) => `case ${x["מזהה תיק פירוק חברה"]}, status ${x["סטטוס תיק"]}, liquidation order ${x["תאריך קבלת צו פירוק"] || "n/a"}, closed ${x["תאריך סגירת תיק"] || "open"}`).join("; ") : "  Official Receiver liquidation file: no record for this number.");
    } catch { out.push("  Official Receiver liquidation file: could not be checked now."); }
  }
  return out;
}

async function uk(name: string): Promise<string[]> {
  const key = process.env.COMPANIES_HOUSE_KEY;
  if (!key || !name) return [];
  const auth = { headers: { Authorization: "Basic " + Buffer.from(key + ":").toString("base64") } };
  const s = await j("https://api.company-information.service.gov.uk/search/companies?items_per_page=3&q=" + encodeURIComponent(name), auth);
  const c = s.items?.[0];
  if (!c) return ["UK Companies House: no matching company."];
  const out = [`UK Companies House, best match by name (verify): ${c.title}, no. ${c.company_number}, status ${c.company_status}, incorporated ${c.date_of_creation || "n/a"}, address ${c.address_snippet || "n/a"}.`];
  try {
    const p = await j(`https://api.company-information.service.gov.uk/company/${c.company_number}/persons-with-significant-control?items_per_page=10`, auth);
    const names = (p.items || []).filter((x: any) => !x.ceased_on).map((x: any) => `${x.name} (${(x.natures_of_control || []).join(", ")})`);
    out.push("  Persons with significant control: " + (names.length ? names.join("; ") : "none listed"));
  } catch { /* optional */ }
  return out;
}


const strip = (n: string) => n.replace(/\b(ltd|limited|inc|llc|gmbh|plc|s\.?a\.?|co\.?)\b\.?/gi, "").replace(/\s+/g, " ").trim();
const isC = (c: string, ...k: string[]) => k.some((x) => c === x || c.startsWith(x + " "));

// Global legal-entity identifier (GLEIF): official LEI record, legal address, status and parent links. No key needed.
async function gleif(name: string): Promise<string[]> {
  const d = await j("https://api.gleif.org/api/v1/lei-records?page%5Bsize%5D=3&filter%5Bentity.legalName%5D=" + encodeURIComponent(name));
  const rs = d.data || [];
  if (!rs.length) return ["GLEIF (global LEI register): no exact legal-name match (many companies have no LEI)."];
  return ["GLEIF (global LEI register), exact legal-name matches, verify identity:", ...rs.map((r: any) => {
    const e = r.attributes?.entity || {}, a = e.legalAddress || {};
    return `- ${e.legalName?.name}, LEI ${r.attributes?.lei}, status ${e.status}, registration ${r.attributes?.registration?.status || "n/a"}, jurisdiction ${e.jurisdiction || "n/a"}, registered no. ${e.registeredAs || "n/a"}, address ${[a.addressLines?.[0], a.city, a.country].filter(Boolean).join(", ")}.`;
  })];
}
async function norway(name: string): Promise<string[]> {
  const d = await j("https://data.brreg.no/enhetsregisteret/api/enheter?size=3&navn=" + encodeURIComponent(strip(name)));
  const rs = d._embedded?.enheter || [];
  if (!rs.length) return ["Norway Bronnoysund Register: no match."];
  return ["Norway Bronnoysund Register (best matches by name, verify):", ...rs.map((r: any) => `- ${r.navn}, org no. ${r.organisasjonsnummer}, ${r.organisasjonsform?.beskrivelse || ""}, registered ${r.registreringsdatoEnhetsregisteret || "n/a"}, employees ${r.antallAnsatte ?? "n/a"}, bankrupt: ${r.konkurs ? "YES" : "no"}, under liquidation: ${r.underAvvikling || r.underTvangsavviklingEllerTvangsopplosning ? "YES" : "no"}, ${r.forretningsadresse?.kommune || ""}.`)];
}
async function france(name: string): Promise<string[]> {
  const d = await j("https://recherche-entreprises.api.gouv.fr/search?per_page=3&q=" + encodeURIComponent(strip(name)));
  const rs = d.results || [];
  if (!rs.length) return ["France Recherche Entreprises: no match."];
  return ["France Recherche Entreprises (best matches by name, verify):", ...rs.map((r: any) => `- ${r.nom_complet}, SIREN ${r.siren}, status ${r.etat_administratif === "A" ? "active" : "ceased"}, created ${r.date_creation || "n/a"}, staff band ${r.tranche_effectif_salarie || "n/a"}, ${r.siege?.libelle_commune || ""}; directors: ${(r.dirigeants || []).slice(0, 3).map((x: any) => x.nom ? `${x.prenoms || ""} ${x.nom}`.trim() : x.denomination).filter(Boolean).join(", ") || "n/a"}.`)];
}
async function finland(name: string): Promise<string[]> {
  const d = await j("https://avoindata.prh.fi/opendata-ytj-api/v3/companies?name=" + encodeURIComponent(strip(name)));
  const rs = (d.companies || []).slice(0, 3);
  if (!rs.length) return ["Finland PRH register: no match."];
  return ["Finland PRH register (best matches by name, verify):", ...rs.map((r: any) => `- ${r.names?.[0]?.name || "?"}, business ID ${r.businessId?.value}, registered ${r.businessId?.registrationDate || "n/a"}, status ${r.status || "n/a"}, form ${r.companyForms?.[0]?.descriptions?.find((x: any) => x.languageCode === "3")?.description || "n/a"}.`)];
}
async function czech(name: string): Promise<string[]> {
  const d = await j("https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty/vyhledat", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ obchodniJmeno: strip(name), pocet: 3, start: 0 }) });
  const rs = d.ekonomickeSubjekty || [];
  if (!rs.length) return ["Czech ARES register: no match."];
  return ["Czech ARES register (best matches by name, verify):", ...rs.map((r: any) => `- ${r.obchodniJmeno}, IC ${r.ico}, ${r.sidlo?.textovaAdresa || ""}, founded ${r.datumVzniku || "n/a"}.`)];
}

// US listed companies: SEC EDGAR (no key; the SEC asks for a contact in the User-Agent).
const SEC_UA = { headers: { "User-Agent": "Sinder Deal Desk research etamar.ramot@gmail.com", Accept: "application/json" } };
let secTickers: { at: number; rows: { cik: number; title: string; ticker: string; n: string }[] } | null = null;
async function edgar(name: string): Promise<string[]> {
  if (!secTickers || Date.now() - secTickers.at > 24 * 3600_000) {
    const d = await j("https://www.sec.gov/files/company_tickers.json", SEC_UA);
    secTickers = { at: Date.now(), rows: Object.values(d).map((x: any) => ({ cik: x.cik_str, title: x.title, ticker: x.ticker, n: norm(x.title).replace(/\b(inc|corp|corporation|co|company|ltd|plc|holdings|group|the)\b/g, "").replace(/\s+/g, " ").trim() })) };
  }
  const q = norm(name).replace(/\b(inc|corp|corporation|co|company|ltd|plc|holdings|group|the)\b/g, "").replace(/\s+/g, " ").trim();
  if (q.length < 3) return [];
  const hit = secTickers.rows.find((r) => r.n === q) || secTickers.rows.find((r) => r.n.startsWith(q + " ") || q.startsWith(r.n + " "));
  if (!hit) return ["SEC EDGAR: no listed US company with this name (private and non-US companies are not in EDGAR)."];
  const sub = await j(`https://data.sec.gov/submissions/CIK${String(hit.cik).padStart(10, "0")}.json`, SEC_UA);
  const f = sub.filings?.recent || {};
  const i10 = (f.form || []).findIndex((x: string) => x === "10-K" || x === "20-F" || x === "40-F");
  return [`SEC EDGAR, name match (verify): ${sub.name}, ticker ${hit.ticker}, CIK ${hit.cik}, SIC ${sub.sic} ${sub.sicDescription || ""}, state of incorporation ${sub.stateOfIncorporation || "n/a"}, fiscal year end ${sub.fiscalYearEnd || "n/a"}; former names: ${(sub.formerNames || []).map((x: any) => x.name).slice(0, 3).join("; ") || "none"}; latest annual report: ${i10 >= 0 ? `${f.form[i10]} filed ${f.filingDate[i10]}` : "n/a"}. Filings: https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${hit.cik}`];
}

export async function registryFacts(name: string, country: string, legalId: string): Promise<string> {
  const c = (country || "").toLowerCase();
  const jobs: Promise<string[]>[] = [];
  if (c === "israel" || c === "ישראל" || /^5\d{8}$/.test(String(legalId || "").replace(/\D/g, ""))) jobs.push(israel(name, legalId));
  if (c.includes("united kingdom") || c === "uk" || c === "gb") jobs.push(uk(name));
  if (name) {
    jobs.push(gleif(name));
    jobs.push(sanctionsFacts(name).then((x) => (x ? [x] : [])));
    if (isC(c, "united states", "usa", "us", "united states of america")) jobs.push(edgar(name));
    if (isC(c, "norway", "nor", "no")) jobs.push(norway(name));
    if (isC(c, "france", "fra", "fr")) jobs.push(france(name));
    if (isC(c, "finland", "fin", "fi")) jobs.push(finland(name));
    if (isC(c, "czechia", "czech republic", "cze", "cz")) jobs.push(czech(name));
  }
  const res = await Promise.allSettled(jobs);
  return res.flatMap((r) => { if (r.status === "fulfilled") return r.value; void logEvent("warn", "registry", "registry check failed", String(r.reason).slice(0, 300)); return ["A registry check failed and was skipped."]; }).join("\n");
}
