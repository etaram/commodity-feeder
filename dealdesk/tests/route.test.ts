// Trade Brain deterministic core (lib/route.ts): every state, the gate rules and the priority vector.
import { evaluateRoute, isBlocked, nextTask, priority, rankRoutes, STATES, WEIGHTS, type EvidenceItem, type OpportunityRoute, type Requirement, type RouteState } from "@/lib/route";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const NOW = "2026-11-11T09:00:00Z";
const evd = (claim: string, source_family: string, status: EvidenceItem["status"] = "observed", valid_until: string | null = null): EvidenceItem =>
  ({ claim, source_family, status, retrieved_at: "2026-11-10T08:00:00Z", valid_until });
const req = (name: string, status: Requirement["status"] = "verified", mandatory = true): Requirement => ({ name, mandatory, status });

// A clean route: everything known, two source families, a live quote, a conversation mandate.
const base = (): OpportunityRoute => ({
  id: "R-1", route_type: "principal_trade", represented_org: "sinder",
  demand: { source_ids: ["T-100"], buyer: "Water Utility", product_spec: "RO membrane 8040, brackish", quantity: 400, unit: "pcs", deadline: "2026-12-01",
    delivery_by: "2027-03-01", status: "open", visibility: "limited" },
  supply: { supplier: "Membrane Co", technical_fit: "supported", requirements: [req("element size 8 inch"), req("NSF/ANSI 61"), req("brochure language", "unknown", false)] },
  evidence: [evd("tender is open", "buyer-portal", "official-source-asserted"), evd("supplier makes 8040 brackish elements", "supplier-site")],
  economics: { price_type: "quote", sale_price: 200000, cost: 160000, capital_need: 90000, funding_limit: 150000, currency: "USD" },
  authority: { owner_mandate: "conversation", sanctions_alert: false, data_rights_ok: true, representation_ok: true, engagement: "none" },
  time: { now: NOW, deadline: "2026-12-01", quote_valid_until: "2026-11-30", lead_time_days: 45 },
});
type Patch = (r: OpportunityRoute) => void;
const mk = (...patches: Patch[]) => { const r = base(); for (const p of patches) p(r); return r; };
const st = (...patches: Patch[]) => evaluateRoute(mk(...patches)).state;
const seen = new Set<RouteState>();
const is = (r: OpportunityRoute, want: RouteState, m: string) => { const e = evaluateRoute(r); seen.add(e.state); ok(e.state === want, `${m}: ${e.state} (want ${want})`); return e; };

// ---- every state ----
const ready = is(mk(), "READY_FOR_AUTHORIZED_CONTACT", "clean route with a mandate");
ok(ready.next_task === null && ready.exact_fit && ready.independently_corroborated && ready.profit_statement === "authoritative", "clean route: exact fit, corroborated, authoritative profit, no next task");
ok(ready.days_left === 20 && ready.economics.margin === 40000, "days left and margin are computed in code (20 days, 40000)");
is(mk((r) => { r.authority.engagement = "in_contact"; }), "ACTIVE", "contact recorded under a mandate");
const review = is(mk((r) => { r.authority.owner_mandate = "none"; }), "READY_FOR_OWNER_REVIEW", "no owner mandate");
ok(review.next_task === null, "approval pending: no next task");
const stopped = is(mk((r) => { r.authority.sanctions_alert = true; }), "STOPPED", "sanctions alert");
ok(stopped.blockers.some((b) => /qualified review required/.test(b.text)) && stopped.next_task === null, "sanctions alert asks for qualified review and offers no task");
is(mk((r) => { r.authority.engagement = "stopped"; }), "STOPPED", "owner stopped the route");
const mismatch = is(mk((r) => { r.supply.requirements[1].status = "contradicted"; }), "MISMATCH", "contradicted mandatory requirement");
ok(mismatch.next_task === null && !mismatch.exact_fit, "mismatch: decisive, no exact fit, no task");
is(mk((r) => { r.supply.technical_fit = "incompatible"; }), "MISMATCH", "incompatible technical fit");
const needs = is(mk((r) => { r.supply.requirements[1].status = "unknown"; }), "NEEDS_EVIDENCE", "unknown mandatory requirement");
ok(!needs.exact_fit && needs.reasons.some((x) => /no exact-fit claim/.test(x)), "unknown requirement: never an exact-fit claim, even with fit 'supported'");
ok(needs.next_task?.kind === "verify_requirement" && /NSF\/ANSI 61/.test(needs.next_task.question), "unknown requirement: the next task names it");
is(mk((r) => { r.supply.technical_fit = "plausible"; }), "NEEDS_EVIDENCE", "plausible fit");
is(mk((r) => { r.supply.technical_fit = "related"; }), "NEEDS_EVIDENCE", "related fit");
const research = is(mk((r) => { r.supply.supplier = null; r.supply.technical_fit = "unknown"; }), "RESEARCH", "no supplier candidate");
ok(research.next_task?.kind === "find_supplier", "no supplier: the next task is to find one");
is(mk((r) => { r.authority.data_rights_ok = null; }), "RESEARCH", "data rights not checked");
const monitor = is(mk((r) => { r.route_type = "supply_winner"; }), "MONITOR", "supply to the winner before the award");
ok(monitor.next_task?.kind === "monitor_award", "monitor: the next task is the award check");
is(mk((r) => { r.demand.status = "planned"; }), "MONITOR", "announced, not open");
is(mk((r) => { r.authority.data_rights_ok = false; }), "INELIGIBLE", "no data rights");
is(mk((r) => { r.authority.representation_ok = false; }), "INELIGIBLE", "representation not allowed");
is(mk((r) => { r.demand.status = "cancelled"; }), "INELIGIBLE", "cancelled demand");
is(mk((r) => { r.time.lead_time_days = 200; }), "INELIGIBLE", "lead time beyond the delivery date");
ok(STATES.every((s) => seen.has(s)), `every state reached at least once (${STATES.filter((s) => !seen.has(s)).join(", ") || "all 9"})`);

// ---- sanctions never auto-clear ----
ok(st((r) => { r.authority.sanctions_alert = true; r.authority.engagement = "in_contact"; r.evidence.push(evd("cleared", "third", "independently-checked")); }) === "STOPPED", "sanctions alert stays STOPPED whatever else is on the route");
ok(st((r) => { r.authority.sanctions_alert = true; r.supply.requirements[0].status = "contradicted"; r.time.deadline = "2026-01-01"; }) === "STOPPED", "access/legal runs first: sanctions outranks mismatch and expiry");
ok(st((r) => { r.supply.requirements[0].status = "contradicted"; r.supply.requirements[1].status = "unknown"; }) === "MISMATCH", "a contradiction outranks unknowns");
ok(st((r) => { r.supply.requirements[2].status = "contradicted"; }) === "READY_FOR_AUTHORIZED_CONTACT", "a non-mandatory requirement does not block");

// ---- time: computed from the dates, per route type ----
const award = (r: OpportunityRoute) => { r.demand.deadline = "2026-11-01"; r.demand.status = "awarded"; };
const primeLate = is(mk((r) => { r.id = "A-prime"; r.route_type = "prime_bid"; r.demand.deadline = "2026-11-01"; r.time.deadline = "2026-11-01"; }), "INELIGIBLE", "prime bid after the bid deadline");
ok(primeLate.blockers.some((b) => b.code === "deadline_expired" && /prime_bid/.test(b.text)) && primeLate.days_left === -10, "expiry names the route type and the days are computed (-10)");
const winner = is(mk(award, (r) => { r.id = "A-winner"; r.route_type = "supply_winner"; r.time.deadline = "2026-12-20"; }), "READY_FOR_AUTHORIZED_CONTACT", "supply to the winner of the same award stays eligible");
ok(winner.reasons.some((x) => /does not bind this route type/.test(x)), "the passed bid deadline is reported, not applied, to the other route type");
ok(st(award, (r) => { r.route_type = "prime_bid"; r.time.deadline = "2026-12-20"; }) === "INELIGIBLE", "prime bid on an awarded demand is ineligible even with a later own deadline");
ok(st((r) => { r.route_type = "prime_bid"; r.time.deadline = null; r.demand.deadline = null; }) === "RESEARCH", "prime bid without any deadline: research, not ready");
ok(evaluateRoute(mk((r) => { r.time.deadline = "2026-11-11"; })).days_left === 0 && st((r) => { r.time.deadline = "2026-11-11"; }) !== "INELIGIBLE", "a date-only deadline runs to the end of that day");
let threw = false; try { evaluateRoute(mk((r) => { r.time.now = "not a date"; })); } catch { threw = true; }
ok(threw, "an unreadable 'now' is an error: the engine does not read the clock");

// ---- authority: no mandate never exceeds owner review ----
const noMandate: Patch = (r) => { r.authority.owner_mandate = "none"; };
ok(st(noMandate, (r) => { r.authority.engagement = "in_contact"; }) === "READY_FOR_OWNER_REVIEW", "no mandate + recorded contact is still owner review, never ACTIVE");
ok(st(noMandate, (r) => { r.evidence.push(evd("x", "third"), evd("y", "fourth", "counterparty-confirmed")); }) === "READY_FOR_OWNER_REVIEW", "no mandate + more evidence is still owner review");
ok(st((r) => { r.authority.owner_mandate = "per_message"; }) === "READY_FOR_AUTHORIZED_CONTACT", "a per-message mandate allows authorized contact");

// ---- finance: null stays null, gaps block the profit statement only ----
const noFin = evaluateRoute(mk((r) => { r.economics = { price_type: "none", sale_price: null, cost: null, capital_need: null, funding_limit: null }; r.time.quote_valid_until = null; }));
ok(noFin.state === "READY_FOR_AUTHORIZED_CONTACT" && noFin.profit_statement === "blocked", "missing finance blocks the profit statement, not the route");
ok(noFin.economics.margin === null && noFin.economics.margin_pct === null && noFin.economics.capital_need === null && noFin.economics.funding_limit === null && noFin.economics.funding_headroom === null,
  "missing numbers stay null in the output (never zero)");
ok(noFin.missing.filter((m) => m.gate === "finance").length === 5, "each missing finance value is listed");
const noFinP = priority(mk((r) => { r.economics = { price_type: "none", sale_price: null, cost: null, capital_need: null, funding_limit: null }; }), noFin)!;
ok(noFinP.economic_quality === null && noFinP.known === 5, "priority: economic_quality is null and is not counted as known");
const zero = evaluateRoute(mk((r) => { r.economics.capital_need = 0; }));
ok(zero.economics.capital_need === 0 && zero.economics.funding_headroom === 150000, "a real zero is kept as zero, distinct from null");
ok(evaluateRoute(mk((r) => { r.economics.price_type = "benchmark"; })).profit_statement === "blocked", "a benchmark price is not an authoritative profit");
const expiredQuote = evaluateRoute(mk((r) => { r.time.quote_valid_until = "2026-11-01"; }));
ok(expiredQuote.profit_statement === "blocked" && expiredQuote.economics.quote_live === false, "an expired quote is not authoritative");
const gap = evaluateRoute(mk((r) => { r.economics.capital_need = 500000; }));
ok(gap.state === "READY_FOR_OWNER_REVIEW" && gap.profit_statement === "blocked" && gap.economics.funding_headroom === -350000, "capital need over the funding limit goes to the owner");
ok(st((r) => { r.supply.supplier = null; r.economics.sale_price = null; }) === "RESEARCH", "missing finance does not stop research");

// ---- evidence ----
const sameFam = evaluateRoute(mk((r) => { r.evidence = [evd("tender is open", "buyer-portal", "official-source-asserted"), evd("tender is open (repost)", "Buyer-Portal ", "independently-checked")]; }));
ok(sameFam.source_families === 1 && !sameFam.independently_corroborated, "two items of one source family count once");
ok(sameFam.state === "READY_FOR_OWNER_REVIEW" && sameFam.blockers.some((b) => b.code === "single_source_family"), "one source family is not independent corroboration, even marked independently-checked");
const weak = evaluateRoute(mk((r) => { r.evidence = [evd("a", "client-deck", "client-asserted"), evd("b", "model", "inferred"), evd("c", "client-call", "client-asserted")]; }));
ok(weak.state === "NEEDS_EVIDENCE" && weak.source_families === 0, "low-confidence evidence alone never counts, whatever its number");
const plusWeak = evaluateRoute(mk((r) => { r.evidence = [evd("tender is open", "buyer-portal"), evd("a", "client-deck", "client-asserted"), evd("b", "model", "inferred")]; }));
ok(plusWeak.source_families === 1 && !plusWeak.independently_corroborated && plusWeak.reasons.some((x) => /2 low-confidence .* not counted/.test(x)),
  "low-confidence items do not upgrade one family to corroborated, and the reasons say so");
const stale = evaluateRoute(mk((r) => { r.evidence[1].valid_until = "2026-11-01"; }));
ok(stale.source_families === 1 && stale.missing.some((m) => m.kind === "refresh_evidence"), "evidence past valid_until is not counted");
const contra = evaluateRoute(mk((r) => { r.evidence.push(evd("supplier makes 8040 brackish elements", "distributor", "contradicted")); }));
ok(contra.state === "NEEDS_EVIDENCE" && contra.next_task?.kind === "resolve_contradiction", "contradicted evidence holds the route and is the next task");
ok(st((r) => { r.evidence.push(evd("old", "x", "superseded"), evd("gap", "y", "missing")); }) === "READY_FOR_AUTHORIZED_CONTACT", "superseded and missing items are not evidence either way");
ok(st((r) => { r.evidence = []; }) === "NEEDS_EVIDENCE", "no evidence at all: needs evidence");

// ---- order of evidence and requirements does not change the result ----
const messy: Patch = (r) => {
  r.supply.requirements.push(req("feed water brackish", "unknown"), req("ISO 9001", "unknown"), req("flow rate", "verified"));
  r.evidence.push(evd("price claim", "distributor", "contradicted"), evd("a", "client-deck", "client-asserted"), evd("old", "buyer-portal", "observed", "2026-11-01"));
};
const fwd = mk(messy), rev = mk(messy, (r) => { r.evidence.reverse(); r.supply.requirements.reverse(); });
const ef = evaluateRoute(fwd), er = evaluateRoute(rev);
ok(JSON.stringify(ef) === JSON.stringify(er), "reversing evidence and requirements gives an identical evaluation");
ok(JSON.stringify(priority(fwd, ef)) === JSON.stringify(priority(rev, er)), "reversing evidence and requirements gives an identical priority vector");
ok(JSON.stringify(evaluateRoute(fwd)) === JSON.stringify(ef), "the same input gives the same output twice");

// ---- next task ----
const two = evaluateRoute(mk((r) => { r.authority.representation_ok = null; r.supply.supplier = null; }));
ok(two.next_task?.kind === "confirm_legal", "of two open questions the cheaper one comes first (a desk check before a supplier search)");
ok(nextTask({ state: "NEEDS_EVIDENCE", missing: [] }) === null && nextTask({ state: "STOPPED", missing: needs.missing }) === null, "nextTask: nothing open or a decisive state gives null");
ok(Object.keys(needs.next_task || {}).sort().join() === "kind,question,why", "next task is a short typed object: kind, question, why");

// ---- priority ----
const p = priority(mk(), ready)!;
const comps = ["fit", "information_edge", "evidence", "execution", "economic_quality", "time_value"] as const;
ok(comps.every((k) => typeof p[k] === "number" && (p[k] as number) >= 0 && (p[k] as number) <= 1) && p.known === 6, "all six components known and inside 0..1");
ok(Math.abs(Object.values(WEIGHTS).reduce((s, x) => s + x, 0) - 1) < 1e-9 && /uncalibrated/.test(p.weights_version), "weights sum to 1 and the version says uncalibrated");
ok(Math.abs(p.weighted_sum - comps.reduce((s, k) => s + WEIGHTS[k] * (p[k] as number), 0)) < 1e-6, "weighted sum is the sum over the components");
ok(!JSON.stringify(p).toLowerCase().includes("probab") && !JSON.stringify(ready).toLowerCase().includes("probab"), "nothing in the output is called a probability");
const sparse = mk((r) => { r.demand.visibility = null; r.demand.delivery_by = null; r.time.lead_time_days = null; });
const ps = priority(sparse, evaluateRoute(sparse))!;
ok(ps.information_edge === null && ps.execution === null && ps.known === 4, "components with missing inputs are null, and known counts the rest");
ok(Math.abs(ps.weighted_sum - (WEIGHTS.fit * ps.fit! + WEIGHTS.evidence * ps.evidence! + WEIGHTS.economic_quality * ps.economic_quality! + WEIGHTS.time_value * ps.time_value!)) < 1e-6, "the sum runs over known components only");
for (const [m, r] of [["STOPPED", mk((x) => { x.authority.sanctions_alert = true; })], ["MISMATCH", mk((x) => { x.supply.technical_fit = "incompatible"; })],
  ["INELIGIBLE", mk((x) => { x.demand.status = "closed"; })]] as const) {
  const e = evaluateRoute(r);
  ok(e.state === m && isBlocked(e.state) && priority(r, e) === null, `priority is null for ${m}`);
}
ok(priority(mk((r) => { r.id = "other"; }), ready) === null, "priority refuses an evaluation that belongs to another route");
ok(priority(mk((r) => { r.authority.sanctions_alert = true; }), ready) !== null && priority(mk((r) => { r.authority.sanctions_alert = true; }), stopped) === null,
  "priority follows the evaluation it is given: the gates decide, not the vector");

// ---- blockers are never averaged away by a high score ----
const star: Patch = (r) => { r.demand.visibility = "private"; r.economics.cost = 100000; r.evidence.push(evd("x", "third"), evd("y", "fourth")); r.time.lead_time_days = 1; };
const modest: Patch = (r) => { r.id = "R-modest"; r.demand.visibility = "public"; r.economics.cost = 195000; r.authority.owner_mandate = "none"; };
const ranked = rankRoutes([mk(star, (r) => { r.id = "R-sanctioned"; r.authority.sanctions_alert = true; }), mk(star, (r) => { r.id = "R-mismatch"; r.supply.requirements[0].status = "contradicted"; }),
  mk(modest), mk(star, (r) => { r.id = "R-star"; })]);
ok(ranked.map((x) => x.route.id).join() === "R-star,R-modest,R-mismatch,R-sanctioned", `order is state first: ${ranked.map((x) => `${x.route.id}=${x.evaluation.state}`).join(" > ")}`);
ok(ranked[2].priority === null && ranked[3].priority === null && ranked[1].priority!.weighted_sum < ranked[0].priority!.weighted_sum, "blocked routes carry no score at all; a modest open route outranks them");
const lowReady = mk((r) => { r.id = "low"; r.demand.visibility = "public"; r.economics.cost = 199000; }), highHold = mk(star, (r) => { r.id = "high"; r.supply.requirements[0].status = "unknown"; });
const pair = rankRoutes([highHold, lowReady]);
ok(pair[0].route.id === "low" && pair[1].priority!.weighted_sum > pair[0].priority!.weighted_sum, "a higher sum does not lift NEEDS_EVIDENCE above a ready route");

console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
