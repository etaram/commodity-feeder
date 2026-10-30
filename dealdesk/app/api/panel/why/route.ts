import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { markets } from "@/lib/markets";
import { claude } from "@/lib/anthropic";

// "Why is this trend happening": a short, sourced explanation of what is driving a commodity group's price move.
// The group and its numbers come from our own data (not from the client), the explanation from a web-searched answer.
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const DAILY_LIMIT = Number(process.env.WHY_DAILY_LIMIT || 60);
const cache = new Map<string, { text: string; at: number }>();
let day = "", used = 0;

export async function POST(req: NextRequest) {
  if (!verifySession((await cookies()).get("dd_session")?.value)) return NextResponse.json({ ok: false }, { status: 401 });
  if (!process.env.ANTHROPIC_API_KEY) return NextResponse.json({ ok: false, error: "AI is not configured" }, { status: 503 });
  const { group, lang } = await req.json().catch(() => ({}));
  const he = lang === "he";
  const m = (await markets()) as { trends?: { group: string; signal: string; m1: number | null; m3: number | null; y1: number | null; series: { name: string; unit: string; month: string; price: number; m1: number | null; m3: number | null; y1: number | null }[] }[] };
  const g = (m.trends || []).find((t) => t.group === group);
  if (!g) return NextResponse.json({ ok: false, error: "Unknown group" }, { status: 400 });
  const month = g.series[0]?.month || "";
  const key = `${g.group}|${month}|${he ? "he" : "en"}`;
  const hit = cache.get(key);
  if (hit && Date.now() - hit.at < 86400000) return NextResponse.json({ ok: true, text: hit.text, cached: true });
  const today = new Date().toISOString().slice(0, 10);
  if (today !== day) { day = today; used = 0; }
  if (used >= DAILY_LIMIT) return NextResponse.json({ ok: false, error: he ? "הגעת למכסה היומית של ההסברים. היא מתאפסת בחצות UTC." : "Daily limit for explanations reached. It resets at midnight UTC." }, { status: 429 });
  used++;
  const rows = g.series.map((s) => `${s.name} (${s.unit}): ${s.price} in ${s.month}; 1m ${s.m1 ?? "-"}%, 3m ${s.m3 ?? "-"}%, 12m ${s.y1 ?? "-"}%`).join("\n");
  const prompt = `You are the market analyst of Sinder, an Israeli procurement and trading firm.
Commodity group: ${g.group}. Our data (World Bank monthly prices, latest month ${month}): group average 1 month ${g.m1 ?? "-"}%, 3 months ${g.m3 ?? "-"}%, 12 months ${g.y1 ?? "-"}%; signal "${g.signal}".
Components:
${rows}

Explain why prices of this group moved this way. Use web search for what is happening now (supply, demand, weather, policy, sanctions, shipping, currency, energy costs), and name which component drove most of the move.
Write in ${he ? "Hebrew" : "English"}, at most 150 words, as 3 to 5 lines each starting with "- ". Separate what is confirmed by sources from what is your inference, and say so if you could not find a clear reason. No emojis, no em-dashes. Never invent figures. End with one line "For a buyer:" with one practical implication for contracts and quotes.`;
  try {
    const { text, sources } = await claude({ max_tokens: 1500, tools: [{ type: "web_search_20250305", name: "web_search", max_uses: 3 }], messages: [{ role: "user", content: prompt }] });
    const src = sources.slice(0, 4).map((s) => `- ${s.title}: ${s.url}`).join("\n");
    const out = (text + (src ? `\n\n${he ? "מקורות" : "Sources"}:\n${src}` : "")).slice(0, 4000);
    if (cache.size > 100) cache.delete(cache.keys().next().value as string);
    cache.set(key, { text: out, at: Date.now() });
    return NextResponse.json({ ok: true, text: out });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 });
  }
}
