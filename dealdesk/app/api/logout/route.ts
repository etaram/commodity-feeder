import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { logActivity } from "@/lib/activity";

export async function POST() {
  const s = verifySession((await cookies()).get("dd_session")?.value);
  if (s) await logActivity(s, "sign_out");
  const res = NextResponse.json({ ok: true });
  res.cookies.set("dd_session", "", { httpOnly: true, secure: true, sameSite: "lax", maxAge: 0, path: "/" });
  return res;
}
