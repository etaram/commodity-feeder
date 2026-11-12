import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { parseFixed, spendReport } from "@/lib/spend";
import FIXED from "@/lib/fixedcosts.json";
import { reservedNow } from "@/lib/anthropic";

// Spending this month (admin panel): per service, spent so far this month against its monthly cap, and the total
// against the total cap, in plain words (lib/spend.ts). Reads the 'AI Usage' ledger and, when it exists, the agents'
// 'Agent Budget' ledger; fixed costs from SPEND_FIXED_COSTS (JSON) or lib/fixedcosts.json. Admin only, read-only.
export const dynamic = "force-dynamic";
export const maxDuration = 30;

const safe = async <T,>(p: Promise<T>, ms = 15000): Promise<T | { error: string }> =>
  Promise.race([p.catch((e) => ({ error: String(e).slice(0, 160) })), new Promise<{ error: string }>((r) => setTimeout(() => r({ error: "timed out" }), ms))]);

export async function GET() {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const [ai, agent] = await Promise.all([
    safe(readRanges(ENGINE_SHEET, ["'AI Usage'!A1:I100000"]).then((g) => { if (!g) throw new Error("the sheets are not configured"); return { rows: g[0] || [] }; })),
    // the ledger tab exists only once the agent roles have run; a missing tab is "not running", not an error
    safe(readRanges(ENGINE_SHEET, ["'Agent Budget'!A1:G50000"]).then((g) => (g ? { rows: g[0] || [] } : null)).catch((e) => (/Unable to parse range|not found|400/i.test(String(e)) ? null : Promise.reject(e)))),
  ]);
  const env = process.env as Record<string, string | undefined>;
  const fixed = parseFixed(env.SPEND_FIXED_COSTS && env.SPEND_FIXED_COSTS.trim() ? env.SPEND_FIXED_COSTS : FIXED);
  return NextResponse.json({ ok: true, ...spendReport({ now: Date.now(), env, ai, agent, fixed, aiReserved: reservedNow() }) });
}
