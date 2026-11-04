import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { addSub, sendPush } from "@/lib/push";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";

// GET: the public key for the browser. POST {subscription, lang}: save this device; a test notification follows.
export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  return NextResponse.json({ ok: true, enabled: !!process.env.VAPID_PUBLIC_KEY, key: process.env.VAPID_PUBLIC_KEY || "" });
}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const sub = b.subscription;
  if (!sub?.endpoint || !sub?.keys?.p256dh || !sub?.keys?.auth) return NextResponse.json({ ok: false, error: "subscription missing" }, { status: 400 });
  const lang = b.lang === "en" ? "en" : "he";
  await addSub(s.email, sub, lang, req.headers.get("user-agent") || "");
  await logActivity(s, "push_subscribe", new URL(sub.endpoint).host, lang);
  const r = await sendPush({ email: s.email, endpoint: sub.endpoint, p256dh: sub.keys.p256dh, auth: sub.keys.auth, lang },
    { title: "Sinder Deal Desk", body: lang === "he" ? "ההתראות פועלות במכשיר הזה." : "Notifications are on for this device.", url: "/#today", tag: "welcome" });
  return NextResponse.json({ ok: true, test: r });
}
