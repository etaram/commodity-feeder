import { num, usd, type Row } from "@/lib/data";

export type Verdict = { action: string; tone: "go" | "watch" | "no"; reasons: string[]; risks: string[]; next: string };

/** Plain-language bottom line for one deal, built only from the engine's own numbers. */
export function verdict(d: Row): Verdict {
  const days = d.days_left === "" ? null : num(d.days_left);
  const ev = num(d.ev_usd), p = num(d.p_win_market), net = num(d.net_margin_pct), value = num(d.deal_value_usd);
  const route = d.route || "direct";
  const reasons: string[] = [], risks: string[] = [];
  if (ev > 0) reasons.push(`expected value ${usd(ev)} after pursuit cost`);
  if (p >= 0.2) reasons.push(`good win odds (${Math.round(p * 100)}%, ~${d.est_bidders || "?"} bidders)`);
  if (net >= 0.08) reasons.push(`healthy net margin (${(net * 100).toFixed(1)}%)`);
  if (num(d.fta_edge_pct) > 0) reasons.push(`trade-agreement edge +${(num(d.fta_edge_pct) * 100).toFixed(1)}% margin`);
  if (d.country === "ISR") reasons.push("home market: no foreign-bidder handicap");
  if (d.value_basis && d.value_basis !== "stated") risks.push(`value is estimated from ${d.value_basis}, not stated`);
  if (p > 0 && p < 0.1) risks.push(`low win odds (${Math.round(p * 100)}%)`);
  if (days !== null && days < 10) risks.push(`only ${days} days to the deadline`);
  if (net > 0 && net < 0.04) risks.push(`thin net margin (${(net * 100).toFixed(1)}%)`);
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

/** Bottom line for a set of deals (Today screen). */
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
