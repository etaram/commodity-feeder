import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { claude } from "@/lib/anthropic";
import { appendRow, sheetsEnabled } from "@/lib/sheets";
import { logEvent } from "@/lib/log";
import { registryFacts } from "@/lib/registry";

// Runs a panel job (research, supplier search, eligibility, logistics, quote...) immediately on the server
// with Claude Haiku 5.5 and web search, writes the finished job to 'Panel Jobs', and returns the answer.
export const maxDuration = 120;
const DAILY_LIMIT = Number(process.env.AI_RUN_DAILY_LIMIT || 80);
let day = "", used = 0;

const GUIDE: Record<string, string> = {
  supplier_search: "Find real companies that can supply this (manufacturers first, then exporters and traders). For each: name, country, what they make, why they fit, official website. Do not stop at Western firms: where emerging markets are major sources of this product (for example China, India, Turkey, Vietnam, Indonesia, Malaysia, Thailand, Brazil, Egypt, South Africa, Ukraine, Kazakhstan), include competitive producers and exporters from there, and say which origin is usually cheapest. Only official public contact details found on the company's own site or an official register, with the source.",
  company_research: "Research this company: what it does, size and ownership, main products and markets, public-sector and export track record, recent news, risks, and how Sinder could work with it.",
  deal_research: "Research this opportunity: who the buyer is and what they buy, budget and timing, who usually wins and at what prices, eligibility for a foreign or Israeli supplier, and the concrete next steps for Sinder.",
  eligibility: "List the threshold (eligibility) conditions for a foreign supplier: registration and legal, financial (turnover, guarantees), technical (experience, certificates), documents, local partner needs, and where the official tender documents are.",
  logistics: "Give practical logistics options to deliver this: likely origin ports, destination port or border point, shipping mode, typical transit time and indicative freight cost range, customs and import rules at destination, and freight forwarders that serve the lane.",
  quote: "Estimate a realistic price: comparable public award prices or market prices with sources, the likely price to win, and the main cost drivers.",
  outreach: "Prepare outreach: who to contact (role, organisation, official channel) and a short professional email draft.",
  company_intel: `Business intelligence (due diligence) on this company, from public sources only. Sections:
1. Identity: legal name, registration number and registry, legal form, status (active / dissolved / in insolvency), founding date, address.
2. Who it is linked to: owners and ultimate beneficial owners where public, parent company and group, main subsidiaries, directors and senior managers (business roles only), notable partners.
3. History: founding, key events, name changes, mergers and acquisitions.
4. Activity volume: revenue, profit, employees (with year), main markets, exports, public contracts won (use our data in the JSON).
5. Credit rating and payment behaviour: public ratings (S&P, Moody's, Fitch or local agencies) if any; public signals such as late-payment reports, insolvency or bankruptcy notices, tax liens, bounced-cheque or restricted-account lists. Say clearly that a full credit report and payment history need a paid provider (for example Dun & Bradstreet, Creditsafe or Coface).
6. Legal and compliance: court cases, arbitration, regulatory fines, debarment (World Bank and other development bank debarment lists), sanctions (OFAC, EU, UN, UK), criminal or corruption investigations.
7. Reputation: recent news, controversies.
8. Red flags and a bottom line for Sinder: low / medium / high risk, and what to verify before signing.
Mark every fact with its source; never guess; write "not found in public sources" where nothing was found.`,
  other: "Answer the request practically.",
};

export async function POST(req: NextRequest) {
  const session = verifySession((await cookies()).get("dd_session")?.value);
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { id, type, target_id, target, context, request, lang } = await req.json().catch(() => ({}));
  if (!target && !request) return NextResponse.json({ ok: false, error: "empty job" }, { status: 400 });
  const today = new Date().toISOString().slice(0, 10);
  if (today !== day) { day = today; used = 0; }
  if (used >= DAILY_LIMIT) return NextResponse.json({ ok: false, error: "Daily research limit reached. It resets at midnight UTC." }, { status: 429 });
  used++;

  const he = lang === "he";
  let verified = "";
  if (type === "company_intel") {
    const cx = (context || {}) as Record<string, string>;
    const nm = String(cx.supplier || cx.Account || "").trim();
    verified = nm ? await registryFacts(nm, String(cx.country || cx.Country || ""), String(cx.legal_id || "")).catch(() => "") : "";
  }
  const prompt = `You are the research analyst of Sinder, an Israeli international procurement and trading firm that supplies public tenders and large buyers worldwide.
Task type: ${type || "other"}. ${GUIDE[type] || GUIDE.other}
Subject: ${String(target || "").slice(0, 400)}
${verified ? `VERIFIED REGISTRY FACTS (official open data, fetched just now; treat as authoritative, quote them under Identity and Legal, and say if a match was by name only):\n${verified}\n` : ""}${request ? `Specific request: ${String(request).slice(0, 1500)}\n` : ""}Data we already have (JSON): ${JSON.stringify(context || {}).slice(0, 6000)}

Use web search to check current facts. Write in ${he ? "Hebrew" : "English"}, practical and short (at most about ${type === "company_intel" ? 600 : 350} words), short headings and lines starting with "- ". No emojis, no em-dashes.
Never invent people, emails, phone numbers or companies; if a fact was not found, say so. Never suggest paying or doing favours for officials.
End with one line "Next step:" saying the single most useful action.`;

  try {
    const { text, sources } = await claude({
      max_tokens: 4000,
      tools: [{ type: "web_search_20250305", name: "web_search", max_uses: type === "company_intel" ? 6 : 3 }],
      messages: [{ role: "user", content: prompt }],
    });
    const src = sources.slice(0, 8).map((s) => `- ${s.title}: ${s.url}`).join("\n");
    const result = (text + (src ? `\n\n${he ? "מקורות" : "Sources"}:\n${src}` : "")).slice(0, 45000);
    const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
    if (sheetsEnabled()) {
      try {
        await appendRow("Panel Jobs", [id || "J" + Date.now().toString(36).toUpperCase(), stamp, type || "other", target_id || "", String(target || "").slice(0, 300),
          JSON.stringify(context || {}).slice(0, 4000), String(request || "").slice(0, 2000), "done", result.slice(0, 20000), sources[0]?.url || "", stamp, `web instant; ${session.email || ""}`]);
      } catch (e) { await logEvent("error", "run", "sheet write failed", String(e).slice(0, 300), session.email); }
    }
    return NextResponse.json({ ok: true, text: result, link: sources[0]?.url || "", updated: stamp });
  } catch (e) {
    await logEvent("error", "run", `${type || "job"} failed`, String((e as Error).message || e), session.email);
    return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 });
  }
}
