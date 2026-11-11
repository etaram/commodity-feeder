import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { loadRoom, roomOn } from "@/lib/roomdata";

export const dynamic = "force-dynamic";

// GET: the operations room as JSON (lib/room.ts), for the caller's workspace. Admins only; the route does not exist
// unless OPS_ROOM=on. Read-only: it starts nothing, approves nothing and sends nothing.
export async function GET() {
  if (!roomOn()) return NextResponse.json({ ok: false }, { status: 404 });
  const { s, res } = await gate("admin");
  if (!s) return res;
  try {
    return NextResponse.json({ ok: true, room: await loadRoom(s.ws) }, { headers: { "cache-control": "no-store" } });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
