import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { queueJob } from "@/lib/sheets";

const TYPES = ["eligibility", "quote", "logistics", "company_research", "deal_research", "supplier_search"];

export async function POST(req: NextRequest) {
  const jar = await cookies();
  const session = verifySession(jar.get("dd_session")?.value);
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { type, targetId = "", target = "", context = "", request = "" } = await req.json().catch(() => ({}));
  if (!TYPES.includes(type)) return NextResponse.json({ ok: false }, { status: 400 });
  try {
    const jobId = await queueJob(type, targetId, target, context, request, session.email);
    return NextResponse.json({ ok: true, jobId });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
