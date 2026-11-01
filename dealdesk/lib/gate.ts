import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { hasRole, type Role, type Session, verifySession } from "./auth";

// Session + role check for API routes: 401 when signed out, 403 {code:"forbidden"} when the role is too low.
export async function gate(min: Role = "viewer"): Promise<{ s: Session; res: null } | { s: null; res: NextResponse }> {
  const s = verifySession((await cookies()).get("dd_session")?.value);
  if (!s) return { s: null, res: NextResponse.json({ ok: false }, { status: 401 }) };
  if (!hasRole(s, min)) return { s: null, res: NextResponse.json({ ok: false, code: "forbidden", error: `This needs the ${min} role` }, { status: 403 }) };
  return { s, res: null };
}
