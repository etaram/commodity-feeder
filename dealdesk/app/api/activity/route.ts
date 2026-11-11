import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity, readActivity, summary } from "@/lib/activity";
import { asWs } from "@/lib/auth";
import { ownWorkspace } from "@/lib/scope";
import { listUsers } from "@/lib/users";

// POST: the panel reports what a signed-in user opens (tab, tender, company), at most once a minute per item per instance.
// GET: admin only, the latest actions, optionally for one user (?email=).
const seen = new Map<string, number>();
const VIEW_ACTIONS = new Set(["view", "open", "search", "filter", "click", "click_out", "time"]);
const perUser = new Map<string, { at: number; n: number }>();

export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const { action, target, detail } = await req.json().catch(() => ({}));
  if (!VIEW_ACTIONS.has(action)) return NextResponse.json({ ok: false }, { status: 400 });
  // at most 400 events an hour per user per instance; the same event at most once a minute (time spent always kept)
  const u = perUser.get(s.email);
  if (!u || Date.now() - u.at > 3600_000) perUser.set(s.email, { at: Date.now(), n: 1 });
  else if (++u.n > 400) return NextResponse.json({ ok: true, dropped: true });
  const key = `${s.email}|${action}|${target}|${action === "time" ? Date.now() : detail}`;
  if (Date.now() - (seen.get(key) || 0) < 60_000) return NextResponse.json({ ok: true, dropped: true });
  seen.set(key, Date.now());
  if (seen.size > 5000) seen.clear();
  await logActivity(s, action, String(target || ""), String(detail || ""));
  return NextResponse.json({ ok: true });
}

export async function GET(req: NextRequest) {
  const { s, res } = await gate("admin");
  if (!s) return res;
  // an admin of another workspace sees the activity of its own accounts only (the log is one tab for everyone)
  const own = ownWorkspace(s.ws);
  const mine = own ? null : new Set((await listUsers()).filter((u) => asWs(u.workspace) === s.ws).map((u) => u.email.toLowerCase()).concat(s.email.toLowerCase()));
  const seen = (email: string) => !mine || mine.has(String(email || "").toLowerCase());
  if (req.nextUrl.searchParams.get("summary")) return NextResponse.json({ ok: true, users: (await summary(Number(req.nextUrl.searchParams.get("days")) || 30)).filter((u) => seen(u.email)) });
  const email = req.nextUrl.searchParams.get("email") || "";
  const limit = Math.min(2000, Math.max(1, Number(req.nextUrl.searchParams.get("limit")) || 500));
  return NextResponse.json({ ok: true, rows: (await readActivity(email, mine ? 50000 : limit)).filter((r) => seen(r.email)).slice(0, limit) });
}
