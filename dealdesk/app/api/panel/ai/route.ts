import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";
import { claude, MODEL } from "@/lib/anthropic";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";

// The panel's quick AI features on the web (quick summary, drafts, free-language search, Hebrew translation).
// Cost controls: cheapest model (Haiku 5.5), capped answer length, cached repeats; a daily count that warns, never refuses.
export const maxDuration = 60;
const MAX_OUT = Number(process.env.AI_MAX_TOKENS || 3000);
const DAILY_LIMIT = Number(process.env.AI_DAILY_LIMIT || 300);
const cache = new Map<string, { text: string; at: number }>();
let day = "", used = 0;

export async function GET() {
  return NextResponse.json({ enabled: Boolean(process.env.ANTHROPIC_API_KEY), model: MODEL });
}

export async function POST(req: NextRequest) {
  const g = await gate("analyst");
  if (!g.s) return g.res;
  if (!process.env.ANTHROPIC_API_KEY) return NextResponse.json({ ok: false, error: "AI is not configured" }, { status: 503 });
  const { prompt } = await req.json().catch(() => ({}));
  if (typeof prompt !== "string" || !prompt) return NextResponse.json({ ok: false }, { status: 400 });
  const input = prompt.slice(0, 20000);
  await logActivity(g.s, "ai_quick", input.replace(/\s+/g, " ").slice(0, 100), `${input.length} chars`);
  // the key carries the workspace: a cached answer is only ever served inside the workspace that asked
  const h = createHash("sha256").update(`${g.s.ws}\n${input}`).digest("hex");
  const hit = cache.get(h);
  if (hit && Date.now() - hit.at < 86400000) return NextResponse.json({ ok: true, text: hit.text, cached: true });
  const today = new Date().toISOString().slice(0, 10);
  if (today !== day) { day = today; used = 0; }
  // calls are never refused (the budget only alerts, lib/anthropic.ts); past the daily count it is logged once
  used++;
  if (used === DAILY_LIMIT + 1) console.warn(`panel ai: ${DAILY_LIMIT} quick calls today on this instance (not refused)`);
  try {
    const { text } = await claude({ max_tokens: MAX_OUT, messages: [{ role: "user", content: input }] }, { job: "panel ai" });
    if (cache.size > 500) cache.delete(cache.keys().next().value as string);
    cache.set(h, { text, at: Date.now() });
    return NextResponse.json({ ok: true, text });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 });
  }
}
