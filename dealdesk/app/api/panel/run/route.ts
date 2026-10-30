import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { claude } from "@/lib/anthropic";
import { appendRow, sheetsEnabled } from "@/lib/sheets";

// Runs a panel job (research, supplier search, eligibility, logistics, quote...) immediately on the server
// with Claude Haiku 5.5 and web search, writes the finished job to 'Panel Jobs', and returns the answer.
export const maxDuration = 60;
const DAILY_LIMIT = Number(process.env.AI_RUN_DAILY_LIMIT || 80);
let day = "", used = 0;

const GUIDE: Record<string, string> = {
  supplier_search: "Find real companies that can supply this (manufacturers first, then exporters and traders). For each: name, country, what they make, why they fit, official website. Only official public contact details found on the company's own site or an official register, with the source.",
  company_research: "Research this company: what it does, size and ownership, main products and markets, public-sector and export track record, recent news, risks, and how Sinder could work with it.",
  deal_research: "Research this opportunity: who the buyer is and what they buy, budget and timing, who usually wins and at what prices, eligibility for a foreign or Israeli supplier, and the concrete next steps for Sinder.",
  eligibility: "List the threshold (eligibility) conditions for a foreign supplier: registration and legal, financial (turnover, guarantees), technical (experience, certificates), documents, local partner needs, and where the official tender documents are.",
  logistics: "Give practical logistics options to deliver this: likely origin ports, destination port or border point, shipping mode, typical transit time and indicative freight cost range, customs and import rules at destination, and freight forwarders that serve the lane.",
  quote: "Estimate a realistic price: comparable public award prices or market prices with sources, the likely price to win, and the main cost drivers.",
  outreach: "Prepare outreach: who to contact (role, organisation, official channel) and a short professional email draft.",
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
  const prompt = `You are the research analyst of Sinder, an Israeli international procurement and trading firm that supplies public tenders and large buyers worldwide.
Task type: ${type || "other"}. ${GUIDE[type] || GUIDE.other}
Subject: ${String(target || "").slice(0, 400)}
${request ? `Specific request: ${String(request).slice(0, 1500)}\n` : ""}Data we already have (JSON): ${JSON.stringify(context || {}).slice(0, 6000)}

Use web search to check current facts. Write in ${he ? "Hebrew" : "English"}, practical and short (at most about 350 words), short headings and lines starting with "- ". No emojis, no em-dashes.
Never invent people, emails, phone numbers or companies; if a fact was not found, say so. Never suggest paying or doing favours for officials.
End with one line "Next step:" saying the single most useful action.`;

  try {
    const { text, sources } = await claude({
      max_tokens: 1800,
      tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 3 }],
      messages: [{ role: "user", content: prompt }],
    });
    const src = sources.slice(0, 8).map((s) => `- ${s.title}: ${s.url}`).join("\n");
    const result = (text + (src ? `\n\n${he ? "מקורות" : "Sources"}:\n${src}` : "")).slice(0, 45000);
    const stamp = new Date().toISOString().slice(0, 16).replace("T", " ");
    if (sheetsEnabled()) {
      try {
        await appendRow("Panel Jobs", [id || "J" + Date.now().toString(36).toUpperCase(), stamp, type || "other", target_id || "", String(target || "").slice(0, 300),
          JSON.stringify(context || {}).slice(0, 4000), String(request || "").slice(0, 2000), "done", result.slice(0, 20000), sources[0]?.url || "", stamp, `web instant; ${session.email || ""}`]);
      } catch (e) { console.error("[run] sheet write failed", String(e).slice(0, 200)); }
    }
    return NextResponse.json({ ok: true, text: result, link: sources[0]?.url || "", updated: stamp });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 });
  }
}
