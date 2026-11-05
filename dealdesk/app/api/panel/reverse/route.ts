import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { claude } from "@/lib/anthropic";
import { supplierSearch, searchTenders, getRange } from "@/lib/panel";
import { appendRow, sheetsEnabled } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";
import { remember } from "@/lib/researchmemory";

// Deal reverse engineering: a screenshot or PDF of a (redacted) deal document comes in, a reconstruction comes out.
// 1. Vision pass (one AI call, no web): the facts the document states, each marked read or inferred, redactions listed.
// 2. The system's own data: proven suppliers of the product, import flows and benchmark price, open tenders, plays.
// 3. Research pass (one AI call, web search): likely counterparties, price sanity, and how Sinder gets into the deal.
// The file is processed in memory and never stored; only the extracted facts go to the job record.
export const maxDuration = 180;
export const dynamic = "force-dynamic";
type Facts = Record<string, unknown> & { product?: string; hs?: string; quantity?: string; unit?: string; incoterm?: string; place?: string; buyer_hints?: string[]; seller_hints?: string[]; date?: string; doc_type?: string; redacted?: string[]; search_terms?: string[] };
const toObjects = (g: string[][]) => { const h = g[0] || []; return g.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""]))); };

export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const data = String(b.data || ""), mime = String(b.mime || ""), text = String(b.text || "").slice(0, 8000), lang = b.lang === "en" ? "en" : "he";
  if (!data && !text) return NextResponse.json({ ok: false, error: "send a file (image or PDF) or text" }, { status: 400 });
  const t0 = Date.now(); console.log(`[reverse] start ${mime} ${Math.round(data.length / 1024)} KB`);
  if (data.length > 6_000_000) return NextResponse.json({ ok: false, error: "file over 4 MB" }, { status: 413 });
  await logActivity(s, "reverse_deal", mime || "text", `${Math.round(data.length / 1024)} KB`);
  const he = lang === "he";
  try {
    // 1. facts
    const ask = `Read this deal document (it may be redacted: grey or black boxes hide names, prices or addresses). Return JSON ONLY:
{"doc_type": "LOI|RFQ|PO|contract|invoice|offer|other", "date": "YYYY-MM-DD or empty", "product": "<as written>", "chemical_or_grade": "", "hs": "<6-digit HS code if you are confident, else empty>",
 "quantity": "<number>", "unit": "MT|t|kg|pcs|...", "incoterm": "", "place": "<named place if any>", "price": "<as written, or 'redacted'>", "currency": "",
 "specs": ["<technical requirements as written>"], "logistics": ["<packaging, tanks, treatment, timing as written>"], "future_volume": "<e.g. 600 MT in 2027>",
 "buyer_hints": ["<any visible clue about the buyer: stamp text, city, legal form, title, language, letterhead colour>"], "seller_hints": ["<clues about the seller>"],
 "redacted": ["<which fields are hidden>"], "search_terms": ["<3-6 English terms to find this product's producers and traders>"], "read": ["<facts actually visible>"], "inferred": ["<your inferences, each marked why>"]}
Rules: quote the document; never invent a name behind a redaction; inferences go only under "inferred".`;
    const content: unknown[] = [];
    if (data) content.push(mime === "application/pdf" ? { type: "document", source: { type: "base64", media_type: "application/pdf", data } } : { type: "image", source: { type: "base64", media_type: mime || "image/png", data } });
    if (text) content.push({ type: "text", text: `Document text:\n${text}` });
    content.push({ type: "text", text: ask });
    const r1 = await claude({ max_tokens: 2000, messages: [{ role: "user", content }] }, { job: "reverse read" });
    const m = r1.text.match(/\{[\s\S]*\}/);
    const f: Facts = m ? JSON.parse(m[0]) : {};
    const product = String(f.product || f.chemical_or_grade || "").slice(0, 120);
    const terms = (Array.isArray(f.search_terms) && f.search_terms.length ? f.search_terms : [product]).map(String).filter(Boolean).slice(0, 4);

    // 2. our own data
    const sup = product ? await supplierSearch({ text: terms[0] || product, strict: true, hs: String(f.hs || "").slice(0, 4) }) : { values: [], total: 0, origins: [] as [string, number][], query: "" };
    const supRows = toObjects(sup.values).slice(0, 8);
    const tv = [[product, "", ""], ["", "", ""], ["", "", ""], ["", "", ""], ["", "", ""]];
    const tenders = product ? toObjects(await searchTenders(tv)).slice(0, 6) : [];
    const hs4 = String(f.hs || "").replace(/\D/g, "").slice(0, 4);
    const markets = hs4 ? toObjects(await getRange("markets")).filter((x) => String(x.hs6 || "").replace(/\D/g, "").startsWith(hs4)).slice(0, 8) : [];
    const own = [
      `Proven suppliers in the universe for "${sup.query || product}": ${sup.total} (origins: ${sup.origins.slice(0, 5).map(([c, n]) => `${c} ${n}`).join(", ") || "-"})`,
      ...supRows.map((x) => `- ${x.supplier} (${x.country}, tier ${x.tier}) ${String(x.products || x.supplied || "").slice(0, 90)}${x.website ? " " + x.website : ""}`),
      tenders.length ? `Open tenders mentioning it: ${tenders.map((t) => `${t.country}: ${String(t.title_en || "").slice(0, 70)} (${t.est_value_usd || "?"}, ${t.deadline || "?"})`).join("; ")}` : "Open tenders mentioning it: none",
      markets.length ? `Import flows (UN Comtrade) for HS ${hs4}: ${markets.map((x) => `${x.country} $${Math.round(Number(x.imports_usd) / 1e6)}M at ${x.unit_value_usd_kg || "?"} $/kg${x.premium_vs_benchmark_pct ? ` (${x.premium_vs_benchmark_pct}% vs benchmark)` : ""}`).join("; ")}` : `Import flows for HS ${hs4 || "?"}: none recorded`,
    ].join("\n");

    // 3. research
    const prompt = `You are the research analyst of Sinder, an Israeli cross-border sourcing and trading firm. A colleague received this (redacted) deal document; reconstruct the deal and say how Sinder could take part.
FACTS EXTRACTED FROM THE DOCUMENT (JSON): ${JSON.stringify(f).slice(0, 4000)}
WHAT OUR OWN DATABASE SAYS:\n${own}
Write in ${he ? "Hebrew" : "English"} (names and products in Latin script), Markdown, at most 450 words, sections exactly:
## ${he ? "מה המסמך אומר" : "What the document says"} (read facts only, as a short list)
## ${he ? "מה אפשר להסיק" : "What can be inferred"} (product identity, chemistry and HS, typical producers and grades, what the logistics clauses reveal about the seller's plant and the buyer's capability, what the redacted price is likely in the range of, citing the source; mark every item "inferred")
## ${he ? "מועמדים לצדדים בעסקה" : "Candidate counterparties"} (up to 5 likely sellers or buyers consistent with the clues: region, EXW collection, product; each with the evidence; say clearly these are candidates, not identifications; use web search to check producers and traders)
## ${he ? "בדיקת מחיר" : "Price check"} (current market price range for the product with sources; compare with any price in the document)
## ${he ? "איך Sinder נכנסת" : "How Sinder gets in"} (3 bullets: supply the buyer from our proven suppliers, broker between the parties, or sell the same product to similar buyers; name the first concrete step)
Never present a guess as a fact. Never invent company names, emails or prices. Mark unknowns.`;
    const r2 = await claude({ max_tokens: 3500, tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 5 }], messages: [{ role: "user", content: prompt }] }, { job: "reverse research" });
    const src = r2.sources.slice(0, 8).map((x) => `- ${x.title}: ${x.url}`).join("\n");
    const result = (r2.text + (src ? `\n\n${he ? "מקורות" : "Sources"}:\n${src}` : "")).slice(0, 45000);
    const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
    if (sheetsEnabled()) {
      try { await appendRow("Panel Jobs", ["RV" + Date.now().toString(36).toUpperCase(), stamp, "reverse", "", `Deal reconstruction: ${product || "document"}`, JSON.stringify(f).slice(0, 4000), "", "done", result.slice(0, 20000), r2.sources[0]?.url || "", stamp, `web instant; ${s.email}`]); } catch { /* the answer still returns */ }
    }
    await logActivity(s, "reverse_deal_done", product, `${sup.total} suppliers, ${tenders.length} tenders`);
    // the reconstruction is kept on the product (code only): its gist, next step and any contacts or ids it printed
    if (product) await remember({ ws: s.ws, by: s.email, job: "reverse", subject: { kind: "product", name: product, key: `product:${product.toLowerCase()}` }, text: r2.text, sources: r2.sources });
    return NextResponse.json({ ok: true, facts: f, text: result, suppliers: supRows, suppliers_total: sup.total, tenders, markets });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 });
  }
}
