import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { queueJob } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

const TYPES = ["eligibility", "quote", "logistics", "company_research", "deal_research", "supplier_search"];

export async function POST(req: NextRequest) {
  const { s: session, res } = await gate("analyst");
  if (!session) return res;
  const { type, targetId = "", target = "", context = "", request = "" } = await req.json().catch(() => ({}));
  if (!TYPES.includes(type)) return NextResponse.json({ ok: false }, { status: 400 });
  try {
    const jobId = await queueJob(type, targetId, target, context, request, session.email);
    await logActivity(session, "job_" + type, target, String(request || "").slice(0, 300));
    return NextResponse.json({ ok: true, jobId });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
