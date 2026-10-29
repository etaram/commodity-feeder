import { NextRequest, NextResponse } from "next/server";

// Optional: the panel's AI features (quick analysis, free-language search, drafts, Hebrew translation) on the web.
// Works only when ANTHROPIC_API_KEY is set in Vercel; otherwise the panel shows that these run inside Claude.
export const maxDuration = 60;
const MODELS = { quick: "claude-haiku-5-5", default: "claude-sonnet-5-5" };

export async function GET() {
  return NextResponse.json({ enabled: Boolean(process.env.ANTHROPIC_API_KEY) });
}

export async function POST(req: NextRequest) {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) return NextResponse.json({ ok: false, error: "AI is not configured" }, { status: 503 });
  const { prompt, tier } = await req.json().catch(() => ({}));
  if (typeof prompt !== "string" || !prompt) return NextResponse.json({ ok: false }, { status: 400 });
  const r = await fetch("https://api.anthropic.com/v1/messages", {
    method: "POST",
    headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
    body: JSON.stringify({ model: process.env.ANTHROPIC_MODEL || MODELS[tier === "quick" ? "quick" : "default"], max_tokens: 2000, messages: [{ role: "user", content: prompt.slice(0, 60000) }] }),
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) return NextResponse.json({ ok: false, error: String(j?.error?.message || r.status).slice(0, 200) }, { status: 502 });
  return NextResponse.json({ ok: true, text: (j.content || []).map((c: { text?: string }) => c.text || "").join("") });
}
