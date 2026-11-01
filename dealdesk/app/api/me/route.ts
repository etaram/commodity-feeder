import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";

// Who is signed in and what they may do; the panel uses it to show the user badge and to hide buttons the role cannot use.
export async function GET() {
  const s = verifySession((await cookies()).get("dd_session")?.value);
  if (!s) return NextResponse.json({ ok: false }, { status: 401 });
  return NextResponse.json({ ok: true, email: s.email, name: s.name, role: s.role, google: Boolean(process.env.GOOGLE_CLIENT_ID) });
}
