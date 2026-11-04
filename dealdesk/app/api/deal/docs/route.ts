import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { claude } from "@/lib/anthropic";
import { clean, readDeal, saveRecord } from "@/lib/deal";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// Reads a tender document (a URL the analyst gives: the notice page, a PDF, a bidding document) and adds every
// mandatory or important requirement it states to the deal's requirements matrix as its own versioned record,
// status "unknown", with the document name and page as the source. One AI call per document, on click only.
// The analyst still marks each item met or not met with evidence; nothing here submits or sends anything.
type Req = { item: string; source_doc: string; page: string; mandatory: boolean; category: string };

export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const dealId = String(b.deal_id || "").slice(0, 120), url = String(b.url || "").trim().slice(0, 500), lang = b.lang === "en" ? "en" : "he";
  if (!dealId || !/^https?:\/\//.test(url)) return NextResponse.json({ ok: false, error: "deal_id and a document URL are required" }, { status: 400 });
  await logActivity(s, "deal_docs", dealId, url);
  const prompt = `Open the tender document at this URL and extract the requirements a bidder must meet: ${url}
Return JSON ONLY, no prose, no code fences: {"document": "<short document name>", "requirements": [{"item": "<one requirement, as the document states it, max 200 chars>", "page": "<page or section, or empty>", "mandatory": true|false, "category": "eligibility|technical|financial|documents|delivery|commercial|other"}]}
Rules: only requirements actually written in the document; mandatory = the document says must / shall / required / minimum / pass-fail; keep numbers, dates, certificates and thresholds exactly; at most 40 items, the mandatory ones first; if the document cannot be opened or holds no requirements, return {"document": "", "requirements": [], "note": "<why>"}.`;
  try {
    const { text } = await claude({ max_tokens: 4000, tools: [{ type: "web_fetch_20250910", name: "web_fetch", max_uses: 2 }], messages: [{ role: "user", content: prompt }] });
    const m = text.match(/\{[\s\S]*\}/);
    const j = m ? JSON.parse(m[0]) : {};
    const items: Req[] = Array.isArray(j.requirements) ? j.requirements : [];
    if (!items.length) return NextResponse.json({ ok: true, added: 0, note: String(j.note || "no requirements found").slice(0, 300) });
    const cur = await readDeal(dealId);
    const have = new Set(cur.records.filter((r) => r.kind === "requirement").map((r) => String(r.data.item || "").toLowerCase().slice(0, 80)));
    let added = 0;
    const doc = String(j.document || "").slice(0, 160) || url.split("/").pop() || "document";
    for (const it of items.slice(0, 40)) {
      const c = clean("requirement", { item: `${it.category ? "[" + it.category + "] " : ""}${it.item}`, source_doc: doc, page: it.page || "", mandatory: it.mandatory !== false, status: "unknown", evidence: "" });
      if (!c.ok || have.has(String(c.data.item).toLowerCase().slice(0, 80))) continue;
      await saveRecord(dealId, "requirement", `R${Date.now().toString(36).toUpperCase()}${added}`, 1, "unknown", c.data, s.email, `from ${url.slice(0, 120)}`);
      added++;
    }
    await logActivity(s, "deal_docs_done", dealId, `${added} requirements from ${doc}`);
    return NextResponse.json({ ok: true, added, document: doc, lang });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 });
  }
}
