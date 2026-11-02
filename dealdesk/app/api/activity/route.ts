import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity, readActivity } from "@/lib/activity";

// POST: the panel reports what a signed-in user opens (tab, tender, company), at most once a minute per item per instance.
// GET: admin only, the latest actions, optionally for one user (?email=).
const seen = new Map<string, number>();
const VIEW_ACTIONS = new Set(["view", "open"]);

export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const { action, target, detail } = await req.json().catch(() => ({}));
  if (!VIEW_ACTIONS.has(action)) return NextResponse.json({ ok: false }, { status: 400 });
  const key = `${s.email}|${action}|${target}`;
  if (Date.now() - (seen.get(key) || 0) < 60_000) return NextResponse.json({ ok: true, dropped: true });
  seen.set(key, Date.now());
  if (seen.size > 5000) seen.clear();
  await logActivity(s, action, String(target || ""), String(detail || ""));
  return NextResponse.json({ ok: true });
}

export async function GET(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const email = req.nextUrl.searchParams.get("email") || "";
  const limit = Math.min(2000, Math.max(1, Number(req.nextUrl.searchParams.get("limit")) || 500));
  return NextResponse.json({ ok: true, rows: await readActivity(email, limit) });
}
