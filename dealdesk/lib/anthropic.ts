// Shared Anthropic API client for the web app. Cheapest model by default (Claude Haiku 5.5).
export const MODEL = process.env.ANTHROPIC_MODEL || "claude-haiku-5-5";

type Block = { type: string; text?: string; citations?: { url?: string; title?: string }[] };

export async function claude(body: Record<string, unknown>): Promise<{ text: string; sources: { url: string; title: string }[] }> {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error("AI is not configured (ANTHROPIC_API_KEY)");
  let messages = body.messages as unknown[];
  const out: Block[] = [];
  for (let turn = 0; turn < 3; turn++) {
    const r = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: { "x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json" },
      body: JSON.stringify({ model: MODEL, ...body, messages }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const msg = `Anthropic ${r.status}: ${String(j?.error?.message || j?.error?.type || "").slice(0, 300)}`;
      console.error("[ai]", msg);
      throw new Error(msg);
    }
    out.push(...((j.content || []) as Block[]));
    if (j.stop_reason !== "pause_turn") break;
    messages = [...messages, { role: "assistant", content: j.content }];
  }
  const text = out.filter((b) => b.type === "text").map((b) => b.text || "").join("").trim();
  const seen = new Set<string>(), sources: { url: string; title: string }[] = [];
  for (const b of out) for (const c of b.citations || []) if (c.url && !seen.has(c.url)) { seen.add(c.url); sources.push({ url: c.url, title: c.title || c.url }); }
  return { text, sources };
}
