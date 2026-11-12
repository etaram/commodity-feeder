import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { buildBrief, buildGeo, readBrief } from "@/lib/brief";
import { logActivity } from "@/lib/activity";
import { broadcast } from "@/lib/telegram";
import { pushAll } from "@/lib/push";

export const dynamic = "force-dynamic";
export const maxDuration = 120;

// GET ?lang=he|en -> today's brief if it exists (no AI). POST {lang} -> build it (one AI call, cached for the day).
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const lang = req.nextUrl.searchParams.get("lang") === "en" ? "en" : "he";
  const geo = req.nextUrl.searchParams.get("kind") === "geo";
  try { return NextResponse.json({ ok: true, brief: await readBrief(geo ? `geo-${lang}` : lang) }); }
  catch (e) { return NextResponse.json({ ok: false, error: `The brief could not be read just now, try again in a minute (${String(e).slice(0, 80)})` }, { status: 503 }); }
}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const lang = b.lang === "en" ? "en" : "he";
  if (b.kind === "geo") {
    try { const g = await buildGeo(lang, s.email); await logActivity(s, "geo", lang, g.cached ? "cached" : `built from ${g.items} sources`); return NextResponse.json({ ok: true, brief: g }); }
    catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
  }
  try {
    const out = await buildBrief(lang, s.email);
    await logActivity(s, "brief", lang, out.cached ? "cached" : `built from ${out.items} items`);
    if (!out.cached && out.text) void pushAll({ title: lang === "he" ? "התקציר העולמי של היום מוכן" : "Today's world brief is ready", body: out.text.replace(/^## .*$/gm, "").replace(/[#*\[\]]/g, "").trim().slice(0, 140), url: "/#today", tag: "brief" }, lang);
    if (!out.cached && out.text) void broadcast((lang === "he" ? "התקציר העולמי של היום מוכן. /brief לקריאה.\n\n" : "Today's world brief is ready. /brief to read it.\n\n") + out.text.replace(/^## (.*)$/gm, "<b>$1</b>").replace(/\n---[\s\S]*$/, "").slice(0, 1500), lang);
    return NextResponse.json({ ok: true, brief: out });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
