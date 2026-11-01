import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { hasRole, ROLES, verifySession } from "@/lib/auth";
import { listUsers, normEmail, now, publicUser, updateUser } from "@/lib/users";
import { sheetsEnabled } from "@/lib/sheets";
import { logEvent } from "@/lib/log";

// Admin only: list accounts, approve or reject requests, change roles, disable accounts. Password hashes never leave the server.
async function admin() {
  const s = verifySession((await cookies()).get("dd_session")?.value);
  if (!s) return { s: null, res: NextResponse.json({ ok: false }, { status: 401 }) };
  if (!hasRole(s, "admin")) return { s: null, res: NextResponse.json({ ok: false, code: "forbidden", error: "Admins only" }, { status: 403 }) };
  return { s, res: null };
}

export async function GET() {
  const { s, res } = await admin();
  if (!s) return res;
  if (!sheetsEnabled()) return NextResponse.json({ ok: true, users: [] });
  const users = (await listUsers(true)).map(publicUser);
  return NextResponse.json({ ok: true, users });
}

export async function POST(req: NextRequest) {
  const { s, res } = await admin();
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const email = normEmail(String(b.email || ""));
  if (!email) return NextResponse.json({ ok: false, error: "email required" }, { status: 400 });
  const patch: Record<string, string> = {};
  if (b.role !== undefined) {
    if (!ROLES.includes(b.role)) return NextResponse.json({ ok: false, error: "bad role" }, { status: 400 });
    patch.role = b.role;
  }
  if (b.status !== undefined) {
    if (!["pending", "active", "disabled"].includes(b.status)) return NextResponse.json({ ok: false, error: "bad status" }, { status: 400 });
    patch.status = b.status;
    if (b.status === "active") { patch.approved_by = s.email; patch.approved_at = now(); }
  }
  if (typeof b.notes === "string") patch.notes = b.notes.slice(0, 200);
  if (email === s.email && (patch.status === "disabled" || (patch.role && patch.role !== "admin"))) {
    return NextResponse.json({ ok: false, error: "You cannot lock yourself out" }, { status: 400 });
  }
  const u = await updateUser(email, patch);
  if (!u) return NextResponse.json({ ok: false, error: "no such user" }, { status: 404 });
  await logEvent("info", "users", `user ${email}: ${Object.entries(patch).filter(([k]) => k === "role" || k === "status").map(([k, v]) => `${k}=${v}`).join(" ")}`, "", s.email);
  return NextResponse.json({ ok: true, user: publicUser(u) });
}
