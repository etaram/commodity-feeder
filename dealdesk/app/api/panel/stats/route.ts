import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { allTenders } from "@/lib/panel";
import { isClosed } from "@/lib/index";

// GET /api/panel/stats: counts over EVERY open notice the server holds (not the page's loaded subset), for the
// Today infographics. OPEN = a deadline today or later (planned and no-deadline rows are counted separately).
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const num = (v: unknown) => { const n = Number(String(v ?? "").replace(/[^0-9.\-]/g, "")); return Number.isFinite(n) ? n : NaN; };

export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const { rows } = await allTenders();
    const now = new Date(), t0 = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
    const reg = new Map<string, number>(), vreg = new Map<string, number>(), sec = new Map<string, number>(), cty = new Map<string, number>();
    const days = [0, 0, 0, 0, 0, 0];
    let open = 0, verified = 0, noDeadline = 0, planned = 0, fresh = 0, value = 0;
    const add = (m: Map<string, number>, k: string) => m.set(k || "-", (m.get(k || "-") || 0) + 1);
    for (const r of rows as unknown as Record<string, string>[]) {
      if (r.stage === "planned") { planned++; continue; }
      if (r.stage === "exemption") continue;
      const dl = String(r.deadline || "").slice(0, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(dl)) { noDeadline++; continue; }
      if (isClosed(dl)) continue;
      open++;
      // tender gate (leads/tender_gate.py): deep link, named buyer, ISO3 country, real title, not petty local works
      if (r.quality === "verified") { verified++; add(vreg, r.region); }
      add(reg, r.region); add(sec, r.sector); add(cty, String(r.country || "").split(",")[0]);
      const d = Math.round((Date.parse(dl) - t0) / 86400000);
      days[d <= 7 ? 0 : d <= 14 ? 1 : d <= 30 ? 2 : d <= 60 ? 3 : d <= 90 ? 4 : 5]++;
      if (r.new === "NEW") fresh++;
      const v = num(r.est_value_usd); if (Number.isFinite(v) && v > 0 && v < 5e10) value += v;
    }
    const top = (m: Map<string, number>, n: number) => [...m.entries()].sort((a, b) => b[1] - a[1]).slice(0, n);
    const countries = [...cty.keys()].filter((c) => /^[A-Z]{3}$/.test(c)).length;
    return NextResponse.json({ ok: true, at: new Date().toISOString(), open, verified, verified_region: top(vreg, 20), no_deadline: noDeadline, planned, fresh, value_usd: Math.round(value),
      countries, region: top(reg, 20), sector: top(sec, 8), country: top(cty, 10), days });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
