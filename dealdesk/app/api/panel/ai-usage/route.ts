import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { budgetState } from "@/lib/anthropic";
import { ENGINE_SHEET, readRanges, UNIVERSE } from "@/lib/sheets";

// Model cost by job (spec section 14): calls, tokens, web searches, estimated cost and latency per job per day, and
// cost per accepted outcome where the outcome is counted in a tab (verified capability facts, briefs). Admin only.
export const dynamic = "force-dynamic";
export async function GET(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const days = Math.min(90, Math.max(1, Number(req.nextUrl.searchParams.get("days")) || 7));
  const since = new Date(Date.now() - days * 864e5).toISOString().slice(0, 10);
  const [usage, verified] = await Promise.all([
    readRanges(ENGINE_SHEET, ["'AI Usage'!A1:K20000"]).then((g) => g?.[0] || []).catch(() => []),
    readRanges(UNIVERSE, ["'Verified capabilities'!G2:H20000"]).then((g) => g?.[0] || []).catch(() => []),
  ]);
  type Agg = { calls: number; errors: number; input: number; output: number; searches: number; usd: number; ms: number };
  const byJob: Record<string, Agg> = {}, byDay: Record<string, number> = {};
  for (const r of usage) {
    const day = String(r[0] || "").slice(0, 10);
    if (day < since) continue;
    const job = String(r[1] || "unnamed");
    const a = (byJob[job] = byJob[job] || { calls: 0, errors: 0, input: 0, output: 0, searches: 0, usd: 0, ms: 0 });
    a.calls++; a.errors += r[10] === "error" ? 1 : 0; a.input += Number(r[4]) || 0; a.output += Number(r[5]) || 0; a.searches += Number(r[7]) || 0; a.usd += Number(r[8]) || 0; a.ms += Number(r[9]) || 0;
    byDay[day] = (byDay[day] || 0) + (Number(r[8]) || 0);
  }
  // accepted outcomes: verified facts (label not unknown) written by the model agent in the window
  const facts = verified.filter((r) => String(r[0] || "") >= since && /model/.test(String(r[1] || ""))).length;
  const jobs = Object.entries(byJob).map(([job, a]) => ({ job, ...a, usd: Math.round(a.usd * 1000) / 1000, avg_ms: a.calls ? Math.round(a.ms / a.calls) : 0,
    per_outcome: job === "verify capability" && facts ? { outcome: "verified facts", n: facts, usd_each: Math.round((a.usd / facts) * 1000) / 1000 } : null })).sort((x, y) => y.usd - x.usd);
  return NextResponse.json({ ok: true, days, since, budget: await budgetState(), jobs, by_day: byDay, note: "Costs are estimates from list prices per token and per web search; the provider invoice is the measured figure." });
}
