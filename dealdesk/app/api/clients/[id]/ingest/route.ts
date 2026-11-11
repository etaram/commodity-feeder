import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { ingest } from "@/lib/dossier";

export const dynamic = "force-dynamic";
export const maxDuration = 120;
type Ctx = { params: Promise<{ id: string }> };

// POST /api/clients/:id/ingest {file: base64, filename} | {url, crawl?: boolean}
// Extracts the text natively (PDF text layer, PPTX slides, or up to 8 pages of the official site), one model call
// per chunk for claims, validated in code; saves a new draft version.
// Upload limits (lib/docextract.ts sniffUpload): 4.5 MB; PDF or PPTX only, decided from the file's bytes (the name and
// the declared type are ignored); a PPTX package is refused above 2,000 entries or 40 MB decompressed; macro-enabled
// decks (PPTM, PPSM) are refused and nothing in a file is ever executed. Uploaded text is data: it cannot approve a
// claim, start a message or change a status; instruction-like passages are stored as flagged quotations.
// -> {ok, version, doc, added, rejected:[{item, reason}], gaps:[{ref, reason}], skipped?, status_reset, status} | {ok:false, error}
export async function POST(req: NextRequest, { params }: Ctx) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const { id } = await params;
  if (Number(req.headers.get("content-length") || 0) > 6_400_000) return NextResponse.json({ ok: false, error: "the file is larger than 4.5 MB" }, { status: 413 });
  const b = await req.json().catch(() => ({}));
  const url = String(b.url || "").trim().slice(0, 500), file = typeof b.file === "string" ? b.file.replace(/^data:[^,]*,/, "") : "";
  if (!url && !file) return NextResponse.json({ ok: false, error: "send a file (base64) or a url" }, { status: 400 });
  if (file.length > 6_200_000) return NextResponse.json({ ok: false, error: "the file is larger than 4.5 MB" }, { status: 413 });
  try {
    const r = await ingest(s.ws, id, url ? { url, crawl: b.crawl !== false } : { file: Buffer.from(file, "base64"), filename: String(b.filename || "").slice(0, 160) }, s.email);
    if (!r.ok) return NextResponse.json({ ok: false, error: r.error }, { status: r.status });
    await logActivity(s, "client_ingest", id, `${r.doc?.name || url || "file"}: +${r.added} claims, ${r.rejected.length} rejected, ${r.gaps.length} gaps, ${(r.flagged || []).length} flagged passages${r.duplicate ? " (already ingested)" : ""}`);
    return NextResponse.json(r);
  } catch (e) { return NextResponse.json({ ok: false, error: String((e as Error).message || e).slice(0, 300) }, { status: 502 }); }
}
