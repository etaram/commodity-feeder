import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { clean, pipeline, readDeal, saveRecord, type Kind } from "@/lib/deal";
import { logActivity } from "@/lib/activity";

export const dynamic = "force-dynamic";

// Private deal workspace data. Analysts and admins only (viewers never receive quotes, prices or requirements):
// the check is here on the server, not only in the panel. Saving never sends anything outside the system.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  if (req.nextUrl.searchParams.get("pipeline") === "1") {
    try { return NextResponse.json({ ok: true, deals: await pipeline(s.ws) }); } catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
  }
  const id = String(req.nextUrl.searchParams.get("id") || "").slice(0, 120);
  if (!id) return NextResponse.json({ ok: false, error: "deal id is required" }, { status: 400 });
  try {
    const r = await readDeal(id, s.ws);
    return NextResponse.json({ ok: true, ...r });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}

// POST {deal_id, kind: quote|requirement|economics, record_id?, data, delete?}: a new version of one record.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const dealId = String(b.deal_id || "").slice(0, 120), kind = String(b.kind || "") as Kind;
  if (!dealId || !["quote", "requirement", "economics", "party", "stage"].includes(kind)) return NextResponse.json({ ok: false, error: "deal_id and kind are required" }, { status: 400 });
  try {
    const cur = await readDeal(dealId, s.ws);
    const recordId = String(b.record_id || (kind === "economics" ? "econ" : kind === "stage" ? "stage" : `${kind[0].toUpperCase()}${Date.now().toString(36).toUpperCase()}`)).slice(0, 60);
    const prev = cur.records.find((r) => r.kind === kind && r.record_id === recordId);
    const version = (prev?.version || 0) + 1;
    if (b.delete) {
      await saveRecord(dealId, kind, recordId, version, "deleted", prev?.data || {}, s.email, "deleted", s.ws);
      await logActivity(s, "deal_" + kind + "_delete", dealId, recordId);
      return NextResponse.json({ ok: true, record_id: recordId, version });
    }
    const c = clean(kind, (b.data || {}) as Record<string, unknown>);
    if (!c.ok) return NextResponse.json({ ok: false, error: c.error }, { status: 400 });
    await saveRecord(dealId, kind, recordId, version, c.status, c.data, s.email, "", s.ws);
    await logActivity(s, "deal_" + kind, dealId, `${recordId} v${version}`);
    return NextResponse.json({ ok: true, record_id: recordId, version });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
