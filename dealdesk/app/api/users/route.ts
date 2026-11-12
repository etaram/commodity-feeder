import { NextRequest, NextResponse } from "next/server";
import { asWs, ROLES } from "@/lib/auth";
import { gate } from "@/lib/gate";
import { ownWorkspace } from "@/lib/scope";
import { listUsers, normEmail, now, publicUser, updateUser } from "@/lib/users";
import { sheetsEnabled } from "@/lib/sheets";
import { logEvent } from "@/lib/log";
import { logActivity } from "@/lib/activity";

// Admin only: list accounts, approve or reject requests, change roles, disable accounts. Password hashes never leave the server.
// An admin manages the accounts of its own workspace; only the original workspace's admins see every workspace and
// can move an account between workspaces. Membership is re-read on every call (lib/gate.ts).
async function admin() {
  return gate("admin");
}
const sameWs = (s: { ws: string }, u: { workspace?: string }) => ownWorkspace(s.ws) || asWs(u.workspace) === s.ws;

export async function GET() {
  const { s, res } = await admin();
  if (!s) return res;
  if (!sheetsEnabled()) return NextResponse.json({ ok: true, users: [] });
  // a cold or slow Users read is retried once; a second failure answers with a reason instead of an empty 500
  try {
    const all = await listUsers(true).catch(() => listUsers(true));
    return NextResponse.json({ ok: true, users: all.filter((u) => sameWs(s, u)).map(publicUser) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: `The Users tab could not be read just now (${String((e as Error)?.message || e).slice(0, 80)}). Try again.` }, { status: 503 });
  }
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
  if (b.workspace !== undefined) {
    if (!ownWorkspace(s.ws)) return NextResponse.json({ ok: false, code: "forbidden", error: "Only the original workspace can move accounts" }, { status: 403 });
    patch.workspace = asWs(b.workspace);
  }
  const target = (await listUsers(true)).find((u) => u.email === email);
  if (target && !sameWs(s, target)) return NextResponse.json({ ok: false, error: "no such user" }, { status: 404 });
  if (email === s.email && (patch.status === "disabled" || (patch.role && patch.role !== "admin"))) {
    return NextResponse.json({ ok: false, error: "You cannot lock yourself out" }, { status: 400 });
  }
  const u = await updateUser(email, patch);
  if (!u) return NextResponse.json({ ok: false, error: "no such user" }, { status: 404 });
  await logActivity(s, "user_admin", email, Object.entries(patch).filter(([k]) => ["role", "status", "workspace"].includes(k)).map(([k, v]) => `${k}=${v}`).join(" "));
  await logEvent("info", "users", `user ${email}: ${Object.entries(patch).filter(([k]) => k === "role" || k === "status").map(([k, v]) => `${k}=${v}`).join(" ")}`, "", s.email);
  return NextResponse.json({ ok: true, user: publicUser(u) });
}
