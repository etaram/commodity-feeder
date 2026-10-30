import { NextRequest, NextResponse } from "next/server";
import { createHash } from "crypto";

// The panel's AI features on the web (quick summary, more info, drafts, free-language search, Hebrew translation).
// Cost controls: every request runs on the cheapest model (Claude Haiku) unless ANTHROPIC_MODEL overrides it,
// answers are capped in length, identical requests are served from cache, and a daily cap stops runaway use.
export const maxDuration = 60;
const MODEL = process.env.ANTHROPIC_MODEL || "claude-haiku-5-5";
const MAX_OUT = Number(process.env.AI_MAX_TOKENS || 1200);
const MAX_IN_CHARS = 20000;
const DAILY_LIMIT = Number(process.env.AI_DAILY_LIMIT || 300);

const cache = new Map<string, { text: string; at: number }>();
const TTL = 24 * 3600 * 1000;
let day = "", used = 0;

export async function GET() {
  return NextResponse.json({ enabled: Boolean(process.env.ANTHROPIC_API_KEY), model: MODEL });
}

export async function POST(req: NextRequest) {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return NextResponse.json({ ok: false, error: "AI is not configured" }, { status: 503 });
  const { prompt } = await req.json().catch(() => ({}));
  if (typeof prompt !== "string" || !prompt) return NextResponse.json({ ok: false }, { status: 400 });
  const input = prompt.slice(0, MAX_IN_CHARS);
  const h = createHash("sha256").update(input).digest("hex");
  const hit = cache.get(h);
  if (hit && Date.now() - hit.at < TTL) return NextResponse.json({ ok: true, text: hit.text, cached: true });

  const today = new Date().toISOString().slice(0, 10);
  if (today !== day) { day = today; used = 0; }
  if (used >= DAILY_LIMIT) return NextResponse.json({ ok: false, error: "Daily AI limit reached. It resets at midnight UTC." }, { status: 429 });
  used++;

  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model: MODEL, max_tokens: MAX_OUT, messages: [{ role: "user", content: input }] }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json({ ok: false, error: String(j?.error?.message || r.status).slice(0, 200) }, { status: 502 });
  const text = (j.content || []).map((c: { text?: string }) => c.text || "").join("");
  if (cache.size > 500) cache.delete(cache.keys().next().value as string);
  cache.set(h, { text, at: Date.now() });
  return NextResponse.json({ ok: true, text });
}
