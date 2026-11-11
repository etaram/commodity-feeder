import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { readDeal } from "@/lib/deal";
import { compareQuotes } from "@/lib/quotes";
import { tenders } from "@/lib/index";
import { routeState } from "@/lib/routemap";

export const dynamic = "force-dynamic";

// GET ?id=DEAL: the route state of one deal in the caller's workspace: { evaluation, priority, next_task }.
// Read only: it reads the deal records and the quote comparison, maps them (lib/routemap.ts) and runs the
// deterministic engine (lib/route.ts). No model call, nothing stored, nothing sent. Analysts and admins only, as for
// the deal records themselves; the workspace comes from the session, never from the request.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const id = String(req.nextUrl.searchParams.get("id") || "").slice(0, 120);
  if (!id) return NextResponse.json({ ok: false, error: "deal id is required" }, { status: 400 });
  try {
    const { records } = await readDeal(id, s.ws);
    const comparison = records.some((r) => r.kind === "quote") ? await compareQuotes(id, s.ws).catch(() => null) : null;
    const t = (await tenders().catch(() => [])).find((x) => x.id === id);
    const view = routeState(records, comparison, new Date().toISOString(),
      { deal_id: id, workspace: s.ws, tender: t ? { stage: t.st || "", deadline: t.dl || "", buyer: t.b || "", title: t.t || "", link: t.l || "" } : null });
    return NextResponse.json({ ok: true, deal_id: id, records: records.length, ...view });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
