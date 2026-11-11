import { num, usd, type Row } from "@/lib/data";

export type Verdict = { action: string; tone: "go" | "watch" | "no"; reasons: string[]; risks: string[]; next: string };

// Bidders as the engine recorded them: the "why" line carries the basis ("3 bidders (buyer history)"). A count that is
// only the engine default (leads/brain.py DEFAULT_BIDS) is not a finding about this deal.
export function biddersBasis(d: Row): { n: number | null; src: string; assumed: number | null } {
  const n = parseFloat(d.est_bidders || ""), src = ((d.why || "").match(/bidders(?: expected)? \(([^)]+)\)/) || [])[1] || "";
  if (!Number.isFinite(n) || n <= 0) return { n: null, src: "", assumed: null };
  return src && src !== "default" ? { n, src, assumed: null } : { n: null, src: "", assumed: n };
}
export const NO_WIN_PROBABILITY = "No win probability is calculated: no outcome data exists.";
export function biddersText(d: Row) {
  const b = biddersBasis(d);
  return b.n !== null ? `about ${b.n} bidders expected (${b.src})` : b.assumed !== null ? `bidders unknown (engine assumed ${b.assumed})` : "bidders unknown";
}

export function verdict(d: Row): Verdict {
  const days = d.days_left === "" ? null : num(d.days_left);
  const ev = num(d.ev_usd), net = num(d.net_margin_pct), value = num(d.deal_value_usd), b = biddersBasis(d);
  const route = d.route || "direct";
  const reasons: string[] = [], risks: string[] = [];
  if (ev > 0) reasons.push(`engine ranking value ${usd(ev)} (a model figure from assumed competition and a sector-typical margin, not this deal's quotes)`);
  if (b.n !== null && b.n <= 3) reasons.push(`about ${b.n} bidders expected (${b.src})`);
  if (net >= 0.08) reasons.push(`sector-typical net margin ${(net * 100).toFixed(1)}%, not this deal's (no quote yet)`);
  if (num(d.fta_edge_pct) > 0) reasons.push(`trade-agreement edge +${(num(d.fta_edge_pct) * 100).toFixed(1)}% margin`);
  if (d.country === "ISR") reasons.push("home market: no foreign-bidder handicap");
  if (d.value_basis && d.value_basis !== "stated") risks.push(`value is estimated from ${d.value_basis}, not stated`);
  if (b.assumed !== null) risks.push(`number of bidders unknown: the engine assumed ${b.assumed}`);
  if (days !== null && days < 10) risks.push(`only ${days} days to the deadline`);
  if (net > 0 && net < 0.04) risks.push(`thin sector-typical net margin ${(net * 100).toFixed(1)}%, not this deal's (no quote yet)`);
  if (d.incumbent) risks.push(`incumbent supplier: ${d.incumbent.slice(0, 60)}`);
  if (/rising/.test(d.price_signal || "")) risks.push(`input prices ${d.price_signal} - fix prices carefully`);
  if (num(d.press_count) > 0) risks.push(`buyer is in the news (${d.press_count} articles) - read before bidding`);

  let action = "Skip", tone: Verdict["tone"] = "no", next = "No action needed.";
  if (d.decision === "Pursue") {
    tone = "go";
    if (route === "direct") { action = "Bid directly"; next = "Run the eligibility check and send RFQs to 3 suppliers this week."; }
    else if (route === "via local partner") { action = "Bid with your local partner"; next = "Send the notice to your partner today and agree on the split before requesting quotes."; }
    else if (route === "needs local partner") { action = "Bid only with a local partner"; next = "Find a local partner first (agent or distributor that already sells to this buyer)."; }
    else { action = "Sell to the winner"; next = "Track the award, then offer materials to the winning contractor."; }
    if (days !== null && days < 10) next = "Decide today - " + next.charAt(0).toLowerCase() + next.slice(1);
  } else if (d.decision === "Watch") {
    tone = "watch";
    action = route === "sub-supply to the winner" ? "Track and sell to the winner" : "Keep on watch";
    next = route === "sub-supply to the winner"
      ? "Note the award date; approach the winner with a materials offer."
      : value > 0 ? "Revisit if the documents show a larger scope or fewer bidders." : "Open the notice to confirm the scope and value.";
  }
  return { action, tone, reasons: reasons.slice(0, 4), risks: risks.slice(0, 4), next };
}

export function portfolioLine(deals: Row[]) {
  const pursue = deals.filter((d) => d.decision === "Pursue");
  const ev = pursue.reduce((s, d) => s + num(d.ev_usd), 0);
  const byRegion = new Map<string, number>();
  for (const d of pursue) byRegion.set(d.region || "Other", (byRegion.get(d.region || "Other") || 0) + num(d.ev_usd));
  const regions = [...byRegion.entries()].sort((a, b) => b[1] - a[1]);
  const urgent = pursue.filter((d) => d.days_left !== "" && num(d.days_left) >= 0 && num(d.days_left) <= 10).length;
  const partner = pursue.filter((d) => (d.route || "").includes("partner")).length;
  return { count: pursue.length, ev, regions: regions.slice(0, 3), urgent, partner };
}
