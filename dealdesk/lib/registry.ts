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

export async function registryFacts(name: string, country: string, legalId: string): Promise<string> {
  const c = (country || "").toLowerCase();
  const jobs: Promise<string[]>[] = [];
  if (c === "israel" || c === "ישראל" || /^5\d{8}$/.test(String(legalId || "").replace(/\D/g, ""))) jobs.push(israel(name, legalId));
  if (c.includes("united kingdom") || c === "uk" || c === "gb") jobs.push(uk(name));
  const res = await Promise.allSettled(jobs);
  return res.flatMap((r) => (r.status === "fulfilled" ? r.value : ["A registry check failed and was skipped."])).join("\n");
}
