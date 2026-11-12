import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { clean, pipeline, readDeal, saveRecord, type Kind } from "@/lib/deal";
import { logActivity } from "@/lib/activity";
import { dealGates as gates } from "@/lib/dealgates";
import { approvalStates, saveDraftEdit } from "@/lib/draftsend";
import { draftHistory } from "@/lib/deal";
import { canMoveDeal, canMoveParty } from "@/lib/transitions";
import { logQuoteReceived } from "@/lib/outcomelog";

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
    // drafts: the live state of each submitted draft's approval (the owner's decision and the send result) and
    // every saved version (who, when, which text revision)
    const drafts = r.records.filter((x) => x.kind === "draft");
    const approvals = drafts.length ? await approvalStates(drafts.map((x) => String((x.data.approval as { id?: string } | undefined)?.id || ""))).catch(() => ({})) : {};
    const draft_history = drafts.length ? await draftHistory(id, s.ws).catch(() => []) : [];
    return NextResponse.json({ ok: true, ...r, approvals, draft_history, ...(await gates(id, r.records)) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}

// POST {deal_id, kind: quote|requirement|economics|party|stage|draft, record_id?, data, delete?}: a new version of one
// record. A draft is kept on the deal only: it is never sent from here and creates no approval request (that is
// POST /api/deal/draft, "Submit for approval"). A draft with the owner, sent or possibly sent cannot be changed.
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const dealId = String(b.deal_id || "").slice(0, 120), kind = String(b.kind || "") as Kind;
  if (!dealId || !["quote", "requirement", "economics", "party", "stage", "draft"].includes(kind)) return NextResponse.json({ ok: false, error: "deal_id and kind are required" }, { status: 400 });
  try {
    const cur = await readDeal(dealId, s.ws);
    const recordId = String(b.record_id || (kind === "economics" ? "econ" : kind === "stage" ? "stage" : `${kind[0].toUpperCase()}${Date.now().toString(36).toUpperCase()}`)).slice(0, 60);
    const prev = cur.records.find((r) => r.kind === kind && r.record_id === recordId);
    const version = (prev?.version || 0) + 1;
    if (kind === "draft" && !b.delete) {
      const r = await saveDraftEdit({ dealId, ws: s.ws, by: s.email, draftId: b.record_id ? recordId : undefined, data: (b.data || {}) as Record<string, unknown> });
      if (!r.ok) return NextResponse.json({ ok: false, code: r.code, error: r.error }, { status: r.status });
      if (!r.unchanged) await logActivity(s, "deal_draft", dealId, `${r.record_id} v${r.version} rev${r.rev}`);
      return NextResponse.json(r);
    }
    if (kind === "draft" && prev && ["submitted", "sent", "delivery_unknown"].includes(prev.status)) return NextResponse.json({ ok: false, code: "draft_locked", error: "A draft with the owner, sent or possibly sent cannot be deleted." }, { status: 409 });
    if (b.delete) {
      await saveRecord(dealId, kind, recordId, version, "deleted", prev?.data || {}, s.email, "deleted", s.ws);
      await logActivity(s, "deal_" + kind + "_delete", dealId, recordId);
      return NextResponse.json({ ok: true, record_id: recordId, version });
    }
    const c = clean(kind, (b.data || {}) as Record<string, unknown>);
    if (!c.ok) return NextResponse.json({ ok: false, error: c.error }, { status: 400 });
    if (prev && prev.status !== "deleted") {
      const mv = kind === "stage" ? canMoveDeal(String(prev.data.stage || ""), String(c.data.stage || ""))
        : kind === "party" ? canMoveParty(String(prev.data.status || prev.status || ""), String(c.data.status || c.status || "")) : { ok: true };
      if (!mv.ok) return NextResponse.json({ ok: false, error: mv.why }, { status: 409 });
    }
    await saveRecord(dealId, kind, recordId, version, c.status, c.data, s.email, "", s.ws);
    await logActivity(s, "deal_" + kind, dealId, `${recordId} v${version}`);
    // outcome ledger: the first version of a quote record is "quote received". Never blocks the save: a failed ledger
    // write is logged (lib/outcomelog.ts) and the answer is the same.
    if (kind === "quote" && version === 1) await logQuoteReceived({ workspace: s.ws, deal_id: dealId, at: new Date().toISOString(), actor: s.email, counterparty: String(c.data.supplier || ""),
      record_id: recordId, source_ref: String(c.data.source_ref || "") }).catch(() => {});
    return NextResponse.json({ ok: true, record_id: recordId, version });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
