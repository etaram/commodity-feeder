// Production dependencies of the mission runner (lib/missionrun.ts): the mission store on Sheets, the deal file, the
// tender and award indexes, the supplier index and the sanctions index. Read only, and no model is called: the
// supplier search runs with noExpand (no query expansion), and the runner refuses a non-Latin product name before it
// gets here, so the translation path of lib/panel.ts is never reached.
import { readDeal } from "@/lib/deal";
import { tenders, winners } from "@/lib/index";
import { sheetsMissionStore } from "@/lib/missionstore-sheets";
import type { Candidate, RunContext, RunDeps } from "@/lib/missionrun";
import { supplierSearch } from "@/lib/panel";
import { compareQuotes } from "@/lib/quotes";
import { screenParties } from "@/lib/sanctions";
import type { Bucket } from "@/lib/supmatch";

const BUCKETS: Bucket[] = ["supported", "plausible", "related", "incompatible"];

export function liveRunDeps(workspace: string): RunDeps {
  return {
    store: sheetsMissionStore(), now: () => Date.now(), workspace,
    async context(m): Promise<RunContext> {
      const now = new Date().toISOString();
      if (!m.deal_id) return { now, records: [], tender: null, award: null, comparison: null };
      const { records } = await readDeal(m.deal_id, workspace);
      const comparison = records.some((r) => r.kind === "quote") ? await compareQuotes(m.deal_id, workspace).catch(() => null) : null;
      const t = (await tenders().catch(() => [])).find((x) => x.id === m.deal_id);
      const w = (await winners().catch(() => ({ rows: [] as Awaited<ReturnType<typeof winners>>["rows"] }))).rows.find((x) => x.id === m.deal_id);
      return { now, records, comparison,
        tender: t ? { stage: t.st || "", deadline: t.dl || "", buyer: t.b || "", title: t.t || "", link: t.l || "" } : null,
        award: w && w.w?.length ? { winner: w.w.join("; "), source: w.l || "", date: w.d || "" } : null };
    },
    async suppliers(query): Promise<Candidate[] | null> {
      try {
        const res = await supplierSearch({ text: query, strict: true, n: 12, noExpand: true });
        const h = res.values[0] || [], col = (k: string) => h.indexOf(k);
        const at = (r: (string | number)[], k: string) => (col(k) < 0 ? "" : String(r[col(k)] ?? ""));
        return res.values.slice(1).map((r) => ({ name: at(r, "supplier"), country: at(r, "country"),
          match: { bucket: (BUCKETS.includes(at(r, "match") as Bucket) ? at(r, "match") : "related") as Bucket, why: at(r, "match_why"), evidence: at(r, "match_evidence"),
            conflicts: at(r, "match_conflicts").split("; ").filter(Boolean), gaps: at(r, "match_gaps").split("; ").filter(Boolean), url: at(r, "match_url") || undefined } }));
      } catch { return null; }
    },
    screen: screenParties,
  };
}
