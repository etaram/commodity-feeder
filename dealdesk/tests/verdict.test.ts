// The bottom line never presents an engine default as a finding (review finding 9): no win-odds percentage, margins
// named as sector-typical, bidders only with their recorded basis.
import { verdict, biddersText, NO_WIN_PROBABILITY } from "@/lib/verdict";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const base = { decision: "Pursue", route: "direct", days_left: "20", ev_usd: "50000", p_win_market: "0.25", net_margin_pct: "0.09", deal_value_usd: "2000000", est_bidders: "4.0", why: "deal $2,000,000 (stated) x net 9.0%; 4 bidders (default); foreign win rate 10% (sector)" };
const v = verdict(base), all = [...v.reasons, ...v.risks].join(" | ");
ok(!/win odds|win chance|win prob/i.test(all) && !/25%/.test(all), "no win odds and no win percentage");
ok(!/healthy net margin|good win/.test(all), "no unqualified praise");
ok(/sector-typical net margin 9\.0%, not this deal's/.test(all), "the margin is named as sector-typical, not this deal's");
ok(/number of bidders unknown: the engine assumed 4/.test(v.risks.join(" | ")), "a default bidder count is an assumption and a risk");
ok(/engine ranking value \$50K \(a model figure/.test(all), "the engine value states its basis");
const h = verdict({ ...base, est_bidders: "2.0", net_margin_pct: "0.03", why: "2 bidders (buyer history)" });
ok(h.reasons.includes("about 2 bidders expected (buyer history)") && !h.risks.some((x) => /bidders unknown/.test(x)), "a recorded bidder count is shown with its source");
ok(h.risks.some((x) => /thin sector-typical net margin 3\.0%, not this deal's/.test(x)), "a thin margin is named as sector-typical");
ok(biddersText({ est_bidders: "", why: "" }) === "bidders unknown" && biddersText(base) === "bidders unknown (engine assumed 4)", "bidders text: unknown, or the assumed default");
ok(/No win probability is calculated/.test(NO_WIN_PROBABILITY), "the plain statement exists");
process.exit(fail ? 1 : 0);
