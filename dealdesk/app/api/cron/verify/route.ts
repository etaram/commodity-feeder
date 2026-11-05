import { NextRequest, NextResponse } from "next/server";
import { runVerification } from "@/lib/verify";
import { backfillJobs } from "@/lib/researchmemory";

// The verification agent (lib/verify.ts), twice a day. Vercel sends "Authorization: Bearer <CRON_SECRET>".
export const dynamic = "force-dynamic";
export const maxDuration = 300;

export async function GET(req: NextRequest) {
  const secret = process.env.CRON_SECRET;
  if (!secret || req.headers.get("authorization") !== `Bearer ${secret}`) return NextResponse.json({ ok: false }, { status: 401 });
  try {
    const v = await runVerification();
    // research memory: past research jobs not yet in the ledger (idempotent, bounded, code only)
    const memory = await backfillJobs(300).catch((e) => ({ error: String(e).slice(0, 160) }));
    return NextResponse.json({ ok: true, ...v, memory });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
