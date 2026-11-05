import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { budgetState, MODEL } from "@/lib/anthropic";
import { MATCH_VERSION } from "@/lib/supmatch";
import { ENGINE_SHEET, readRanges, UNIVERSE } from "@/lib/sheets";
import { getSourceQuality, getSources } from "@/lib/data";
import { intel } from "@/lib/intel";
import { getRange } from "@/lib/panel";
import { readAssertions } from "@/lib/assertionstore";

// The admin panel's data in one call: system health, data volumes and quality, matching measurements, verification
// and assertion counts, model usage, recent warnings. Every part is read independently and fails on its own, so one
// slow sheet never blanks the panel. Numbers are what the stores hold now; nothing is estimated here except AI cost.
export const dynamic = "force-dynamic";
export const maxDuration = 60;

const safe = async <T,>(p: Promise<T>, ms = 12000): Promise<T | { error: string }> =>
  Promise.race([p.catch((e) => ({ error: String(e).slice(0, 160) })), new Promise<{ error: string }>((r) => setTimeout(() => r({ error: "timed out" }), ms))]);
const n = (v: unknown) => { const x = Number(v); return Number.isFinite(x) ? x : 0; };

export async function GET() {
  const { s, res } = await gate("admin");
  if (!s) return res;
  const since14 = new Date(Date.now() - 14 * 864e5).toISOString().slice(0, 10);
  const [classif, evalTab, verified, assertions, sources, quality, ai, applog, volumes, world] = await Promise.all([
    safe(readRanges(UNIVERSE, ["'Classification check'!A1:L28"]).then((g) => {
      const v = g?.[0] || [];
      const hi = v.findIndex((r) => r[0] === "sector");
      const rows = hi < 0 ? [] : v.slice(hi + 1).filter((r) => r[0] && r[1] && !isNaN(Number(r[1])));
      return { built: String(v[0]?.[0] || ""), head: hi < 0 ? [] : v[hi], rows };
    })),
    safe(readRanges(UNIVERSE, ["'Search eval'!A1:J48"]).then((g) => {
      const v = g?.[0] || [];
      const buckets = v.filter((r) => /^bucket '/.test(String(r[0] || ""))).map((r) => r[0]);
      const hi = v.findIndex((r) => r[0] === "query" && r[1] === "results now");
      const queries = hi < 0 ? [] : v.slice(hi + 1).filter((r) => r[0] && r[0] !== "query").map((r) => ({ query: r[0], results: n(r[1]), supported: n(r[3]), plausible: n(r[4]), related: n(r[5]), human: r[6] || "", web: r[8] || "" }));
      return { buckets, queries };
    })),
    safe(readRanges(UNIVERSE, ["'Verified capabilities'!A2:H20000"]).then((g) => {
      const v = g?.[0] || [];
      const by = (i: number) => v.reduce((m, r) => { const k = String(r[i] || "-"); m[k] = (m[k] || 0) + 1; return m; }, {} as Record<string, number>);
      const recent = v.filter((r) => String(r[6] || "") >= since14);
      const byDay = recent.reduce((m, r) => { const d = String(r[6]).slice(0, 10); m[d] = (m[d] || 0) + 1; return m; }, {} as Record<string, number>);
      return { total: v.length, by_label: by(3), by_method: by(7), last14_by_day: byDay };
    })),
    safe(readAssertions().then((rows) => ({ total: rows.length, by_status: rows.reduce((m, r) => { m[r.status] = (m[r.status] || 0) + 1; return m; }, {} as Record<string, number>),
      by_property: rows.reduce((m, r) => { m[r.property] = (m[r.property] || 0) + 1; return m; }, {} as Record<string, number>) }))),
    safe(getSources()),
    safe(getSourceQuality()),
    safe(readRanges(ENGINE_SHEET, ["'AI Usage'!A1:K20000"]).then((g) => {
      const v = g?.[0] || [];
      const days: Record<string, number> = {}, jobs: Record<string, { calls: number; usd: number; errors: number; searches: number; ms: number }> = {};
      for (const r of v) {
        const d = String(r[0] || "").slice(0, 10); if (d < since14) continue;
        days[d] = (days[d] || 0) + n(r[8]);
        const j = (jobs[String(r[1] || "unnamed")] ||= { calls: 0, usd: 0, errors: 0, searches: 0, ms: 0 });
        j.calls++; j.usd += n(r[8]); j.errors += r[10] === "error" ? 1 : 0; j.searches += n(r[7]); j.ms += n(r[9]);
      }
      return { days, jobs: Object.entries(jobs).map(([job, a]) => ({ job, ...a, usd: Math.round(a.usd * 1000) / 1000, avg_ms: a.calls ? Math.round(a.ms / a.calls) : 0 })).sort((a, b) => b.usd - a.usd) };
    })),
    safe(readRanges(ENGINE_SHEET, ["'App Log'!A1:H3000"]).then((g) => {
      const v = (g?.[0] || []).filter((r) => r[1] === "error" || r[1] === "warn");
      // collapse repeats: same level, area and message counted once with the latest time
      const m = new Map<string, { time: string; level: string; area: string; message: string; detail: string; count: number }>();
      for (const r of v) { const k = `${r[1]}|${r[2]}|${String(r[3]).replace(/\(\w+\)/g, "()")}`; const x = m.get(k); if (x) { x.count++; if (String(r[0]) > x.time) x.time = String(r[0]); } else m.set(k, { time: String(r[0]), level: String(r[1]), area: String(r[2]), message: String(r[3]).slice(0, 200), detail: String(r[4] || "").slice(0, 200), count: 1 }); }
      return [...m.values()].sort((a, b) => b.time.localeCompare(a.time)).slice(0, 40);
    })),
    safe((async () => ({ tenders_open: n((await getRange("tot_t"))[0]?.[1]), suppliers_searchable: n((await getRange("tot_s"))[0]?.[1]) }))(), 20000),
    safe(intel({}).then((x) => x.counts)),
  ]);
  return NextResponse.json({ ok: true, at: new Date().toISOString(),
    build: { commit: process.env.VERCEL_GIT_COMMIT_SHA || "local", supplier_match: MATCH_VERSION, model: MODEL },
    ai_budget: await budgetState().catch(() => null), volumes, world, classification: classif, search_eval: evalTab, verified, assertions, sources, source_quality: quality, ai, warnings: applog });
}
