import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { DEFAULT_WS } from "@/lib/auth";
import { whoIKnow } from "@/lib/network";

export const dynamic = "force-dynamic";

// POST {names: [...]} -> {matches: {name: [{name, title, company}]}} from the private 'My Network' tab (analysts and admins).
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const names = (Array.isArray(b.names) ? b.names : []).map((x: unknown) => String(x || "").slice(0, 200)).filter(Boolean);
  try {
    // the network is the original workspace owner's private contacts: never shown to another organisation
    if (s.ws !== DEFAULT_WS) return NextResponse.json({ ok: true, matches: {} });
    return NextResponse.json({ ok: true, matches: await whoIKnow(names) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
