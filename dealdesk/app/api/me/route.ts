import { gate } from "@/lib/gate";
import { NextResponse } from "next/server";

// Who is signed in and what they may do; the panel uses it to show the user badge and to hide buttons the role cannot use.
export async function GET() {
  // gate() re-reads the Users tab: the badge and the hidden buttons follow a revoked account or a lowered role at once
  const { s, res } = await gate("viewer");
  if (!s) return res;
  return NextResponse.json({ ok: true, email: s.email, name: s.name, role: s.role, google: Boolean(process.env.GOOGLE_CLIENT_ID) });
}
