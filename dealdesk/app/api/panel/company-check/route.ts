import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { appendRow, gviz, gvizLit, UNIVERSE } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";

// Company checks (leads/company_check.py, a background job every 3 hours, code only): what the supplier's own website
// says. GET ?name=&country= -> the latest check for that company, or null. POST {name, country} (analyst) -> puts the
// company at the front of the next run's queue (tab 'Check queue'). GET ?summary=1 (viewer) -> counts by verdict.
export const dynamic = "force-dynamic";
const COLS = ["key", "supplier", "country", "checked", "verdict", "name_match", "website", "domain", "description", "products", "sector",
  "record_sector", "sector_conflict", "roles", "certificates", "export", "export_countries", "legal_ids", "emails", "phones", "gaps", "reason", "version", "content_hash"];

export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const q = req.nextUrl.searchParams;
  try {
    if (q.get("summary")) {
      const rows = await gviz(UNIVERSE, "Company checks", "select E, count(A) group by E");
      return NextResponse.json({ ok: true, by_verdict: Object.fromEntries(rows.map((r) => [r[0], Number(r[1]) || 0])) });
    }
    const name = String(q.get("name") || "").slice(0, 200), country = String(q.get("country") || "").slice(0, 3);
    if (!name) return NextResponse.json({ ok: false, error: "name is required" }, { status: 400 });
    const rows = await gviz(UNIVERSE, "Company checks", `select * where B = ${gvizLit(name)}${country ? ` and C = ${gvizLit(country)}` : ""} order by D desc limit 1`);
    const r = rows[0];
    return NextResponse.json({ ok: true, check: r ? Object.fromEntries(COLS.map((c, i) => [c, r[i] ?? ""])) : null });
  } catch (e) {
    // the tab appears after the first background run
    return NextResponse.json({ ok: true, check: null, note: String(e).slice(0, 120) });
  }
}

export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const name = String(b.name || "").trim().slice(0, 200), country = String(b.country || "").trim().toUpperCase().slice(0, 3);
  if (!name) return NextResponse.json({ ok: false, error: "name is required" }, { status: 400 });
  await appendRow("Check queue", [new Date().toISOString(), name, country, s.email]);
  await logActivity(s, "company_check_request", name, country);
  return NextResponse.json({ ok: true, queued: true, note: "checked in the next background run (every 3 hours)" });
}
