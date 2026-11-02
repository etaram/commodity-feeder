import { NextRequest, NextResponse } from "next/server";
import { createUser, findUser, hashPassword, normEmail, validEmail } from "@/lib/users";
import { sheetsEnabled } from "@/lib/sheets";
import { logEvent } from "@/lib/log";
import { notifyAccessRequest } from "@/lib/notify";
import { logActivity } from "@/lib/activity";

// Access request: creates a pending account. Nothing is granted until an admin approves it in the panel.
const recent = new Map<string, number[]>();

export async function POST(req: NextRequest) {
  const ip = req.headers.get("x-forwarded-for")?.split(",")[0].trim() || "?";
  const hits = (recent.get(ip) || []).filter((t) => Date.now() - t < 3600_000);
  if (hits.length >= 5) return NextResponse.json({ ok: false, error: "Too many requests, try again later" }, { status: 429 });
  recent.set(ip, [...hits, Date.now()]);

  const { email, name, passcode } = await req.json().catch(() => ({}));
  const e = normEmail(String(email || ""));
  const n = String(name || "").trim();
  const p = String(passcode || "");
  if (!validEmail(e)) return NextResponse.json({ ok: false, error: "Enter a valid email address" }, { status: 400 });
  if (n.length < 2 || n.length > 80) return NextResponse.json({ ok: false, error: "Enter your full name" }, { status: 400 });
  if (p.length < 10 || p.length > 200) return NextResponse.json({ ok: false, error: "Password: at least 10 characters" }, { status: 400 });
  if (!sheetsEnabled()) return NextResponse.json({ ok: false, error: "Sign-up is not available right now" }, { status: 503 });

  if (await findUser(e, true)) return NextResponse.json({ ok: false, error: "This email already has an account (or a pending request)" }, { status: 409 });
  await createUser(e, n, "password", hashPassword(p));
  await logEvent("info", "users", "access request", `${e} (${n})`, e).catch(() => {});
  await notifyAccessRequest(e, n, "password", req.nextUrl.origin);
  await logActivity({ email: e, name: n, role: "viewer" }, "access_request", "", "password");
  return NextResponse.json({ ok: true, status: "pending" });
}
