import { extractFacts, subjectOf, METHOD } from "@/lib/researchmemory";
let n = 0, bad = 0; const ok = (c: boolean, m: string) => { n++; if (!c) { bad++; console.log("FAIL", m); } };
const now = new Date("2026-11-05T10:00:00Z");
const text = `Acme Valves Ltd is an Israeli maker of butterfly valves (https://www.acmevalves.co.il/about). It holds ISO 9001 and WRAS.
Sales: sales@acmevalves.co.il, +972 4 123 4567. A reseller lists it at dealer@resellers.com and on https://www.linkedin.com/company/acme.
Company No. 512345678.

Next step: ask sales@ for a quote on DN300 valves.

Sources:
- Acme: https://www.acmevalves.co.il/`;
const f = extractFacts({ ws: "sinder", by: "a@b.c", job: "company_research", subject: { kind: "supplier", name: "Acme Valves Ltd", country: "ISR" }, text, sources: [{ url: "https://www.acmevalves.co.il/" }] }, now);
const by = (p: string) => f.filter((a) => a.property === p).map((a) => a.value);
ok(by("contact_email").includes("sales@acmevalves.co.il") && !by("contact_email").includes("dealer@resellers.com"), "own-domain e-mail kept as contact");
ok(by("contact_email_other_domain").includes("dealer@resellers.com"), "other-domain e-mail kept apart");
ok(by("contact_phone").includes("+972 4 123 4567"), "phone");
ok(by("website")[0] === "https://acmevalves.co.il/", "website on the company's own domain, not linkedin: " + by("website"));
ok(by("certification").includes("ISO 9001"), "certificate");
ok(by("legal_id").includes("Company no. 512345678"), "registration number");
ok(by("next_step")[0].startsWith("ask sales@"), "next step");
ok(by("research:company_research").length === 1, "the research gist as a note");
ok(f.every((a) => a.status === "inferred" && a.review_method === METHOD && a.ws === "sinder"), "never observed, always the researcher's workspace");
ok(f.every((a) => !!a.expires), "facts expire");
const again = extractFacts({ ws: "sinder", by: "x@y.z", job: "company_research", subject: { kind: "supplier", name: "ACME VALVES LTD.", country: "ISR" }, text, sources: [] }, now);
ok(again.find((a) => a.property === "contact_email")?.id === f.find((a) => a.property === "contact_email")?.id, "same fact found twice has one id");
const other = extractFacts({ ws: "acme", by: "x@y.z", job: "company_research", subject: { kind: "supplier", name: "Acme Valves Ltd", country: "ISR" }, text, sources: [] }, now);
ok(other[0].id !== f[0].id, "another workspace keeps its own copy");
const sup = extractFacts({ ws: "sinder", by: "a", job: "supplier_search", subject: { kind: "product", name: "urea" }, product: "granular urea", text: "Found two.", sources: [],
  suppliers: [{ name: "Fertiglobe", country: "ARE", type: "manufacturer", website: "https://fertiglobe.com", source: "https://fertiglobe.com/products" }, { name: "No Source Co", country: "IND" }] }, now);
ok(sup.some((a) => a.property === "supplies" && a.value === "granular urea" && a.entity_key.startsWith("fertiglobe")), "supplier search: supplies fact on the found company");
ok(!sup.some((a) => a.entity_key.startsWith("no source")), "a company without a source is not kept");
const ct = extractFacts({ ws: "sinder", by: "a", job: "find_contact", subject: { kind: "supplier", name: "Kenya Power", country: "KEN" }, text: "{}", sources: [],
  contacts: { organisation: "Kenya Power", website: "https://kplc.co.ke", contacts: [{ role: "Procurement", email: "Procurement@KPLC.co.ke", source: "https://kplc.co.ke/contact" }, { channel: "e-procurement portal" }] } }, now);
ok(ct.some((a) => a.property === "contact_email" && a.value === "procurement@kplc.co.ke" && a.evidence.url?.includes("kplc.co.ke/contact")), "contact JSON with its page");
ok(ct.some((a) => a.property === "contact_channel" && a.value === "e-procurement portal"), "portal channel kept");
const dd = extractFacts({ ws: "sinder", by: "a", job: "deal_docs", subject: { kind: "project", name: "ITB", key: "tender:T1" }, text: "- [mandatory] ISO 9001 certificate (ITB, p.12)\n- Bid security 2% (ITB, p.3)", sources: [{ url: "https://x/itb.pdf" }] }, now);
ok(dd.filter((a) => a.property === "requirement").length === 2 && dd.every((a) => a.entity_key === "tender:T1"), "tender requirements kept on the tender");
ok(subjectOf("company_intel", "Business intelligence: Acme (ISR)", "BI:Acme", {}).name === "Acme" && subjectOf("company_intel", "Business intelligence: Acme (ISR)", "", {}).country === "ISR", "subject from a BI job title");
ok(subjectOf("deal_research", "Supply of valves", "T-99", {}).key === "tender:T-99", "deal research is about the tender");
console.log(`${n - bad}/${n} research memory checks pass`); if (bad) process.exit(1);
