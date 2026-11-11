import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { readDeal } from "@/lib/deal";
import { compareQuotes } from "@/lib/quotes";
import { tenders } from "@/lib/index";
import { dealParties, routeState, type DealContext } from "@/lib/routemap";
import { screenParties } from "@/lib/sanctions";

export const dynamic = "force-dynamic";

// GET ?id=DEAL: the route state of one deal in the caller's workspace: { evaluation, priority, next_task }.
// Read only: it reads the deal records and the quote comparison, maps them (lib/routemap.ts) and runs the
// deterministic engine (lib/route.ts). The deal's parties are screened by name against the sanctions index
// (lib/sanctions.ts): a candidate match raises the alert (STOPPED), no match reads "checked, no candidate match on
// <date>" (not a clearance), unreadable lists read "not checked". No model call, nothing stored, nothing sent. Analysts and admins only, as for
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
    const now = new Date().toISOString();
    const ctx: DealContext = { deal_id: id, workspace: s.ws, tender: t ? { stage: t.st || "", deadline: t.dl || "", buyer: t.b || "", title: t.t || "", link: t.l || "" } : null };
    ctx.sanctions = await screenParties(dealParties(records, ctx), now); // never throws: unreadable lists read as NOT_CHECKED
    const view = routeState(records, comparison, now, ctx);
    return NextResponse.json({ ok: true, deal_id: id, records: records.length, ...view });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
