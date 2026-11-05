import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { asWs, hasRole, type Role, type Session, verifySession } from "./auth";
import { findUser } from "./users";

// Session + role check for API routes: 401 when signed out, 403 {code:"forbidden"} when the role is too low.
export async function gate(min: Role = "viewer"): Promise<{ s: Session; res: null } | { s: null; res: NextResponse }> {
  let s = verifySession((await cookies()).get("dd_session")?.value);
  if (!s) return { s: null, res: NextResponse.json({ ok: false }, { status: 401 }) };
  // the signed token can be up to 30 days old: role, status and workspace are re-read from the Users tab (cached 30 s),
  // so a revoked membership or a lowered role takes effect at once. The bootstrap team login has no row and keeps
  // its token (as does any token without a row: disabling an account, not deleting its row, is how access is removed);
  // a Users-tab outage keeps the token rather than locking everyone out.
  const u = await findUser(s.email).catch(() => undefined);
  if (u) {
    if (u.status !== "active") return { s: null, res: NextResponse.json({ ok: false, code: "revoked" }, { status: 401 }) };
    s = { ...s, role: u.role, ws: asWs(u.workspace) };
  }
  if (!hasRole(s, min)) return { s: null, res: NextResponse.json({ ok: false, code: "forbidden", error: `This needs the ${min} role` }, { status: 403 }) };
  return { s, res: null };
}

