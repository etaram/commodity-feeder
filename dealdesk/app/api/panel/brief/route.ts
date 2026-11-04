import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { buildBrief, readBrief } from "@/lib/brief";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// GET ?lang=he|en -> today's brief if it exists (no AI). POST {lang} -> build it (one AI call, cached for the day).
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const lang = req.nextUrl.searchParams.get("lang") === "en" ? "en" : "he";
  return NextResponse.json({ ok: true, brief: await readBrief(lang) });
}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const lang = b.lang === "en" ? "en" : "he";
  try {
    const out = await buildBrief(lang, s.email);
    await logActivity(s, "brief", lang, out.cached ? "cached" : `built from ${out.items} items`);
    return NextResponse.json({ ok: true, brief: out });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
