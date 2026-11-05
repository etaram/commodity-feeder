import { filterEvents, rankTimelines, splitHypotheses, touches } from "@/lib/intel";

const ok = (c: boolean, m: string) => { if (!c) { console.error("FAIL:", m); process.exit(1); } };
const ev: Record<string, string>[] = [
  { event_id: "a", type: "award", event_date: "2026-11-01", project_country: "KEN", tier: "high", origin: "record", affected_markets: "" },
  { event_id: "b", type: "trade_policy_change", event_date: "2026-11-03", project_country: "", tier: "medium", origin: "news", affected_markets: "CHN;USA" },
  { event_id: "c", type: "award", event_date: "2026-10-01", project_country: "TZA", supplier_country: "KEN", tier: "low", origin: "record", affected_markets: "" },
];
ok(touches(ev[2], ["KEN"]), "supplier country counts as touching");
ok(filterEvents(ev, {})[0].event_id === "b", "latest first");
ok(filterEvents(ev, { country: "ken" }).length === 2, "country filter is case-insensitive and role-aware");
ok(filterEvents(ev, { type: "award", tier: "medium" }).map((x) => x.event_id).join() === "a", "type + tier filter");
ok(filterEvents(ev, { country: "CHN" })[0].event_id === "b", "affected markets match");
const now = Date.parse("2026-11-05");
const tl = rankTimelines([
  { project_key: "old", last_date: "2025-01-01", value_usd: "900000000", n_events: "3", project_country: "KEN", milestones: "[]" },
  { project_key: "new", last_date: "2026-11-01", value_usd: "50000000", n_events: "5", project_country: "KEN", milestones: '[{"d":"2026-11-01","t":"award"}]' },
], {}, 30, now);
const m0 = tl[0].milestones;
ok(tl[0].project_key === "new" && Array.isArray(m0) && m0.length === 1, "recent timeline first, milestones parsed");
const h = splitHypotheses([
  { status: "actionable", tender_deadline: "2026-11-01", project_country: "KEN" },
  { status: "actionable", tender_deadline: "2026-12-01", project_country: "KEN" },
  { status: "research candidate", project_country: "KEN" },
], {}, 40, "2026-11-05");
ok(h.actionable.length === 1 && h.research.length === 1, "expired tender is not actionable");
console.log("intel: all checks passed");
