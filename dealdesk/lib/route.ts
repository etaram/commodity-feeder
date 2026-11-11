// Trade Brain, deterministic core: one OpportunityRoute in, one state out. Pure code: no model calls, no I/O, no
// clock (the caller supplies time.now), no persistence. See docs/release-2026-11-13/DECISION_ENGINE.md.
//
// A route is ONE way for ONE represented organisation to act on ONE demand with ONE supplier candidate. The same
// award can carry several routes (prime bid, supply to the winner, EPC subcontract ...); each is evaluated alone.
//
// Order of work: the gates run first and decide the state. Ranking (priority) only orders routes that are not
// blocked, and a score can never lift a route out of a blocked state. Nothing here is a probability.
import type { Bucket } from "@/lib/supmatch";
import { cashCheck } from "@/lib/dealstate";

export const ROUTE_TYPES = ["prime_bid", "supply_winner", "epc_subcontract", "agency", "client_bd", "principal_trade"] as const;
export type RouteType = (typeof ROUTE_TYPES)[number];

export type DemandStatus = "planned" | "open" | "awarded" | "closed" | "cancelled" | "unknown";
/** supmatch.ts buckets plus "unknown" (fit not assessed yet). */
export type TechnicalFit = Bucket | "unknown";
export type RequirementStatus = "verified" | "unknown" | "contradicted";
export type Requirement = { name: string; mandatory: boolean; status: RequirementStatus };

export const EVIDENCE_STATUSES = ["observed", "official-source-asserted", "client-asserted", "independently-checked", "counterparty-confirmed",
  "inferred", "contradicted", "missing", "superseded"] as const;
export type EvidenceStatus = (typeof EVIDENCE_STATUSES)[number];
export type EvidenceItem = {
  claim: string;
  source_family: string;       // one publisher / document lineage; copies and reposts share a family
  status: EvidenceStatus;
  retrieved_at: string | null; // ISO
  valid_until: string | null;  // ISO; null = no stated expiry
};

export type PriceType = "quote" | "benchmark" | "assumption" | "none";
export type OwnerMandate = "none" | "per_message" | "conversation";

export type OpportunityRoute = {
  id: string;
  route_type: RouteType;
  represented_org: string;     // workspace id the route acts for
  demand: {
    source_ids: string[];
    buyer: string;
    product_spec: string;
    quantity: number | null;
    unit?: string;
    deadline: string | null;       // the buyer's own published deadline (bid submission); binds prime_bid only
    delivery_by?: string | null;   // required delivery date, when the demand states one
    status: DemandStatus;
    visibility?: "public" | "limited" | "private" | null; // who else can see this demand; null = not assessed
  };
  supply: {
    supplier: string | null;       // supplier candidate; null = none identified yet
    technical_fit: TechnicalFit;
    requirements: Requirement[];
  };
  evidence: EvidenceItem[];
  economics: {                     // every number is nullable: missing is null, never zero
    price_type: PriceType;
    sale_price: number | null;
    cost: number | null;
    capital_need: number | null;
    funding_limit: number | null;
    currency?: string;
  };
  authority: {
    owner_mandate: OwnerMandate;
    sanctions_alert: boolean;
    data_rights_ok: boolean | null;      // null = not checked
    representation_ok: boolean | null;   // null = not checked
    engagement?: "none" | "in_contact" | "stopped"; // recorded by a person; never set by this module
  };
  time: {
    now: string;                         // ISO; supplied by the caller so the result is reproducible
    deadline: string | null;             // this route's own decision deadline
    quote_valid_until: string | null;
    lead_time_days: number | null;
  };
};

export const STATES = ["INELIGIBLE", "MISMATCH", "NEEDS_EVIDENCE", "RESEARCH", "MONITOR", "READY_FOR_OWNER_REVIEW",
  "READY_FOR_AUTHORIZED_CONTACT", "ACTIVE", "STOPPED"] as const;
export type RouteState = (typeof STATES)[number];
export const GATE_ORDER = ["access_legal", "technical_fit", "route_eligibility", "time", "authority", "finance", "evidence"] as const;
export type GateName = (typeof GATE_ORDER)[number];

export type TaskKind = "confirm_legal" | "find_supplier" | "assess_fit" | "verify_requirement" | "check_demand_status" | "confirm_date"
  | "monitor_award" | "resolve_contradiction" | "corroborate_evidence" | "refresh_evidence" | "get_quote" | "confirm_finance";
export type Blocker = { gate: GateName; code: string; text: string; decisive: boolean; state: RouteState };
/** forces: the state this gap holds the route in, or null when the gap does not change the state. cost: 1 (desk check) .. 5 (needs a counterparty). */
export type Missing = { gate: GateName; key: string; kind: TaskKind; question: string; why: string; cost: number; forces: RouteState | null };
export type NextTask = { kind: TaskKind; question: string; why: string };

export type Evaluation = {
  route_id: string;
  route_type: RouteType;
  state: RouteState;
  blockers: Blocker[];
  missing: Missing[];
  reasons: string[];
  next_task: NextTask | null;
  gates: { gate: GateName; outcome: "pass" | "missing" | "blocked" }[];
  exact_fit: boolean;                 // true only when fit is "supported" and no mandatory requirement is unknown or contradicted
  source_families: number;            // distinct families among live, countable evidence
  independently_corroborated: boolean;
  days_left: number | null;           // whole days from now to the binding deadline, computed here
  profit_statement: "authoritative" | "blocked";
  economics: { price_type: PriceType; quote_live: boolean | null; margin: number | null; margin_pct: number | null;
    capital_need: number | null; funding_limit: number | null; funding_headroom: number | null };
};

const BLOCKED_STATES: readonly RouteState[] = ["INELIGIBLE", "MISMATCH", "STOPPED"];
const HOLDING_STATES: readonly RouteState[] = ["NEEDS_EVIDENCE", "RESEARCH", "MONITOR"];
export const isBlocked = (s: RouteState) => BLOCKED_STATES.includes(s);

// Evidence that can count toward corroboration. client-asserted and inferred are low confidence: they are listed in
// the reasons but never counted, whatever their number. missing / superseded are not evidence.
const COUNTABLE: readonly EvidenceStatus[] = ["observed", "official-source-asserted", "independently-checked", "counterparty-confirmed"];
const LOW_CONFIDENCE: readonly EvidenceStatus[] = ["client-asserted", "inferred"];

const DAY = 86_400_000;
const num = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
/** ISO date or date-time to epoch ms; a date without a time means the end of that day (UTC). Unreadable = null. */
export function parseTime(v: string | null | undefined, endOfDay = true): number | null {
  const s = String(v ?? "").trim();
  if (!s) return null;
  const t = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(s) ? `${s}T${endOfDay ? "23:59:59" : "00:00:00"}Z` : s);
  return Number.isFinite(t) ? t : null;
}
const cmp = (a: string, b: string) => (a < b ? -1 : a > b ? 1 : 0);
const famKey = (s: string) => String(s || "").trim().toLowerCase();

type EvidenceView = { families: string[]; live_contradicted: string[]; low_confidence: number; stale: number; total: number };
function evidenceView(items: EvidenceItem[], now: number): EvidenceView {
  const fam = new Set<string>(), contradicted: string[] = []; let low = 0, stale = 0;
  for (const e of items) {
    if (e.status === "missing" || e.status === "superseded") continue;
    const until = parseTime(e.valid_until);
    if (until !== null && until < now) { stale++; continue; }
    if (e.status === "contradicted") contradicted.push(String(e.claim || "").trim());
    else if (LOW_CONFIDENCE.includes(e.status)) low++;
    else if (COUNTABLE.includes(e.status) && famKey(e.source_family)) fam.add(famKey(e.source_family));
  }
  return { families: [...fam].sort(cmp), live_contradicted: contradicted.sort(cmp), low_confidence: low, stale, total: items.length };
}

/** Runs the gates in GATE_ORDER and returns the state. Input order of evidence and requirements does not matter. */
export function evaluateRoute(route: OpportunityRoute): Evaluation {
  const now = parseTime(route.time.now, false);
  if (now === null) throw new RangeError("route.time.now must be an ISO date: the engine does not read the clock");
  const blockers: Blocker[] = [], missing: Missing[] = [], reasons: string[] = [];
  const block = (gate: GateName, code: string, text: string, state: RouteState, decisive = true) => { blockers.push({ gate, code, text, decisive, state }); };
  const miss = (gate: GateName, key: string, kind: TaskKind, question: string, why: string, cost: number, forces: RouteState | null) => { missing.push({ gate, key, kind, question, why, cost, forces }); };
  const a = route.authority, t = route.route_type;

  // ---- 1. access / legal ----
  if (a.sanctions_alert) block("access_legal", "sanctions_alert", "sanctions alert on this route: qualified review required; the alert is never cleared by this engine", "STOPPED");
  if (!String(route.represented_org || "").trim()) block("access_legal", "no_represented_org", "no represented organisation: a route must act for one workspace", "INELIGIBLE");
  if (a.data_rights_ok === false) block("access_legal", "data_rights", "the source data may not be used for this route", "INELIGIBLE");
  else if (a.data_rights_ok == null) miss("access_legal", "authority.data_rights_ok", "confirm_legal", "May the represented organisation use the source data for this route?", "data rights are not checked", 1, "RESEARCH");
  if (a.representation_ok === false) block("access_legal", "representation", "the represented organisation may not be represented on this route", "INELIGIBLE");
  else if (a.representation_ok == null) miss("access_legal", "authority.representation_ok", "confirm_legal", "Is the workspace allowed to act for the represented organisation on this route?", "representation is not checked", 1, "RESEARCH");

  // ---- 2. technical fit (before any ranking; acceptance test F09) ----
  const mandatory = route.supply.requirements.filter((r) => r.mandatory);
  const names = (s: RequirementStatus) => mandatory.filter((r) => r.status === s).map((r) => String(r.name).trim()).sort(cmp);
  const contradicted = names("contradicted"), unknown = names("unknown"), fit = route.supply.technical_fit;
  const hasSupplier = !!String(route.supply.supplier || "").trim();
  if (contradicted.length) block("technical_fit", "requirement_contradicted", `mandatory requirement contradicted: ${contradicted.join("; ")}`, "MISMATCH");
  if (fit === "incompatible") block("technical_fit", "incompatible", "supplier evidence conflicts with the requested product", "MISMATCH");
  if (!hasSupplier) miss("technical_fit", "supply.supplier", "find_supplier", "Which supplier can make exactly the requested product?", "no supplier candidate on this route", 3, "RESEARCH");
  else if (fit === "unknown") miss("technical_fit", "supply.technical_fit", "assess_fit", "Does the supplier's own product evidence state the requested product?", "technical fit is not assessed", 2, "RESEARCH");
  else if (fit === "plausible" || fit === "related") miss("technical_fit", "supply.technical_fit", "assess_fit", "Is there product evidence that the supplier makes the exact requested product?",
    fit === "related" ? "only a related product or role is evidenced" : "only partial product evidence", 2, "NEEDS_EVIDENCE");
  for (const r of unknown) miss("technical_fit", `requirement:${r}`, "verify_requirement", `Does the supplier's evidence state the mandatory requirement "${r}"?`, "mandatory requirement not evidenced", 2, "NEEDS_EVIDENCE");
  const exact_fit = hasSupplier && fit === "supported" && !unknown.length && !contradicted.length;
  if (unknown.length) reasons.push(`${unknown.length} mandatory requirement(s) unknown: no exact-fit claim`);
  reasons.push(exact_fit ? `technical fit supported, ${mandatory.length} mandatory requirement(s) verified` : `technical fit: ${hasSupplier ? fit : "no supplier candidate"} (not an exact fit)`);

  // ---- 3. commercial route eligibility ----
  const ds = route.demand.status;
  if (ds === "cancelled" || ds === "closed") block("route_eligibility", `demand_${ds}`, `the demand is ${ds}`, "INELIGIBLE");
  else if (ds === "unknown") miss("route_eligibility", "demand.status", "check_demand_status", "Is the demand open, awarded or closed at its source?", "demand status is not known", 1, "RESEARCH");
  else if (ds === "planned") miss("route_eligibility", "demand.status", "monitor_award", "Has the buyer published the procurement?", "the demand is announced but not open", 1, "MONITOR");
  else if (t === "prime_bid" && ds === "awarded") block("route_eligibility", "already_awarded", "already awarded: prime_bid is closed for this route type; other route types are evaluated separately", "INELIGIBLE");
  else if (t === "supply_winner" && ds === "open") miss("route_eligibility", "demand.status", "monitor_award", "Has the award been published, and who won?", "supply to the winner starts at the award", 1, "MONITOR");

  // ---- 4. time (computed here from the dates; never taken from a caller-supplied days_left) ----
  const own = parseTime(route.time.deadline), buyer = parseTime(route.demand.deadline);
  const binding = t === "prime_bid" ? (own !== null && buyer !== null ? Math.min(own, buyer) : own ?? buyer) : own;
  const days_left = binding === null ? null : Math.floor((binding - now) / DAY);
  if (binding !== null && binding < now) block("time", "deadline_expired", `deadline passed ${-days_left!} day(s) ago: ${t} is ineligible; other route types for the same demand are evaluated separately`, "INELIGIBLE");
  else if (binding === null) miss("time", "time.deadline", "confirm_date", "What is the deadline for this route?", "no deadline recorded", 1, t === "prime_bid" ? "RESEARCH" : null);
  else reasons.push(`${days_left} day(s) to the deadline`);
  if (t !== "prime_bid" && buyer !== null && buyer < now) reasons.push("the buyer's bid deadline has passed; it does not bind this route type");
  const lead = num(route.time.lead_time_days), delivery = parseTime(route.demand.delivery_by);
  if (lead !== null && delivery !== null && now + lead * DAY > delivery) block("time", "lead_time", `lead time ${lead} day(s) cannot meet the delivery date`, "INELIGIBLE");

  // ---- 5. authority ----
  if (a.engagement === "stopped") block("authority", "owner_stopped", "the owner stopped this route", "STOPPED");
  if (a.owner_mandate === "none") block("authority", "no_owner_mandate", "no owner mandate: nothing may be sent; the owner reviews first", "READY_FOR_OWNER_REVIEW", false);

  // ---- 6. finance (gaps block an authoritative profit statement, never research) ----
  const e = route.economics, sale = num(e.sale_price), cost = num(e.cost), need = num(e.capital_need), limit = num(e.funding_limit);
  const quoteUntil = parseTime(route.time.quote_valid_until);
  const quote_live = e.price_type !== "quote" ? null : quoteUntil === null || quoteUntil >= now;
  if (e.price_type !== "quote") miss("finance", "economics.price_type", "get_quote", "What is the supplier's actual quoted price?", `price basis is ${e.price_type}, not a quote`, 5, null);
  else if (!quote_live) miss("finance", "time.quote_valid_until", "get_quote", "Will the supplier renew the expired quote?", "the quote has expired", 4, null);
  for (const [k, v] of [["sale_price", sale], ["cost", cost], ["capital_need", need], ["funding_limit", limit]] as const)
    if (v === null) miss("finance", `economics.${k}`, "confirm_finance", `What is the ${k.replace("_", " ")}?`, `${k.replace("_", " ")} is missing (null, not zero)`, 3, null);
  const capacity = need === null ? "unknown" : cashCheck([{ day: 0, amount: -need }], 0, limit).funding_capacity;
  if (capacity === "exceeds the stated limit") block("finance", "funding_gap", "capital need exceeds the funding limit: the owner decides on financing", "READY_FOR_OWNER_REVIEW", false);
  const margin = sale !== null && cost !== null ? sale - cost : null;
  const authoritative = e.price_type === "quote" && quote_live === true && margin !== null && capacity === "within the stated limit";
  if (!authoritative) reasons.push("no authoritative profit statement: finance inputs are missing, not a live quote, or over the funding limit");

  // ---- 7. evidence ----
  const ev = evidenceView(route.evidence, now);
  for (const c of [...new Set(ev.live_contradicted)]) {
    block("evidence", "evidence_contradicted", `contradicted evidence: ${c || "(unnamed claim)"}`, "NEEDS_EVIDENCE", false);
    miss("evidence", `contradiction:${c}`, "resolve_contradiction", `Which source is right about "${c}"?`, "a live claim is contradicted", 2, "NEEDS_EVIDENCE");
  }
  if (!ev.families.length) miss("evidence", "evidence.countable", "corroborate_evidence", "Is there a primary source (official notice, document, counterparty) for the core claim?",
    ev.low_confidence ? "only low-confidence evidence (client-asserted or inferred), which is not counted" : "no live evidence", 2, "NEEDS_EVIDENCE");
  else if (ev.families.length < 2) {
    block("evidence", "single_source_family", "evidence comes from one source family: not independently corroborated", "READY_FOR_OWNER_REVIEW", false);
    miss("evidence", "evidence.second_family", "corroborate_evidence", "Does a second, independent source confirm the core claim?", "one source family only", 2, null);
  }
  if (ev.stale) miss("evidence", "evidence.stale", "refresh_evidence", "Are the expired evidence items still true at their source?", `${ev.stale} evidence item(s) past valid_until are not counted`, 2, null);
  if (ev.low_confidence) reasons.push(`${ev.low_confidence} low-confidence evidence item(s) listed but not counted`);
  reasons.push(`${ev.families.length} independent source famil${ev.families.length === 1 ? "y" : "ies"}`);

  // ---- state: decisive blockers first, then holding states, each in gate order; a score is never consulted ----
  const gi = (g: GateName) => GATE_ORDER.indexOf(g);
  blockers.sort((x, y) => gi(x.gate) - gi(y.gate) || cmp(x.code, y.code) || cmp(x.text, y.text));
  missing.sort((x, y) => gi(x.gate) - gi(y.gate) || cmp(x.key, y.key));
  const decisive = blockers.find((b) => b.decisive);
  const holds = [...blockers.filter((b) => HOLDING_STATES.includes(b.state)).map((b) => ({ gate: b.gate, state: b.state })),
    ...missing.filter((m) => m.forces).map((m) => ({ gate: m.gate, state: m.forces as RouteState }))].sort((x, y) => gi(x.gate) - gi(y.gate));
  let state: RouteState;
  if (decisive) state = decisive.state;
  else if (holds.length) state = holds[0].state;
  else if (blockers.length) state = "READY_FOR_OWNER_REVIEW";
  else state = a.engagement === "in_contact" ? "ACTIVE" : "READY_FOR_AUTHORIZED_CONTACT";
  if (a.owner_mandate === "none" && a.engagement === "in_contact") reasons.push("contact is recorded without an owner mandate: review required");
  if (state === "ACTIVE" && a.owner_mandate === "per_message") reasons.push("mandate is per message: each outgoing message still needs approval");
  for (const b of blockers) reasons.push(`${b.decisive ? "blocker" : "limit"} (${b.gate}): ${b.text}`);

  const gates = GATE_ORDER.map((gate) => ({ gate, outcome: blockers.some((b) => b.gate === gate) ? "blocked" as const : missing.some((m) => m.gate === gate) ? "missing" as const : "pass" as const }));
  return {
    route_id: route.id, route_type: t, state, blockers, missing, reasons, next_task: nextTask({ state, missing }), gates, exact_fit,
    source_families: ev.families.length, independently_corroborated: ev.families.length >= 2, days_left,
    profit_statement: authoritative ? "authoritative" : "blocked",
    economics: { price_type: e.price_type, quote_live, margin, margin_pct: margin !== null && sale !== null && sale > 0 ? margin / sale : null,
      capital_need: need, funding_limit: limit, funding_headroom: need !== null && limit !== null ? limit - need : null },
  };
}

/** The single cheapest open question that would move the route out of its current state. Null when a decision is
 *  reached (ACTIVE, READY_FOR_AUTHORIZED_CONTACT), a decisive blocker is confirmed (INELIGIBLE, MISMATCH, STOPPED)
 *  or approval is pending (READY_FOR_OWNER_REVIEW). Ties: gate order, then key. */
export function nextTask(evaluation: Pick<Evaluation, "state" | "missing">): NextTask | null {
  if (!HOLDING_STATES.includes(evaluation.state)) return null;
  const gi = (g: GateName) => GATE_ORDER.indexOf(g);
  const open = evaluation.missing.filter((m) => m.forces !== null).sort((x, y) => x.cost - y.cost || gi(x.gate) - gi(y.gate) || cmp(x.key, y.key));
  return open.length ? { kind: open[0].kind, question: open[0].question, why: open[0].why } : null;
}

// PROPOSED MANAGEMENT WEIGHTS, NOT CALIBRATED: 0.20, 0.20, 0.15, 0.20, 0.15, 0.10. They state what management wants
// to look at first; they were not fitted to outcomes and the weighted sum is an ordering aid, not a likelihood of
// anything. Change the version string with any change to the weights or to a component formula.
export const WEIGHTS_VERSION = "proposed-management-weights-1 (2026-11-11, uncalibrated)";
export const WEIGHTS = { fit: 0.20, information_edge: 0.20, evidence: 0.15, execution: 0.20, economic_quality: 0.15, time_value: 0.10 } as const;
export type Component = keyof typeof WEIGHTS;
export type Priority = { [K in Component]: number | null } & { known: number; weighted_sum: number; weights_version: string };

const clamp = (x: number) => Math.min(1, Math.max(0, x));
const FIT_BASE: Record<TechnicalFit, number | null> = { supported: 1, plausible: 0.5, related: 0.25, incompatible: 0, unknown: null };
const VISIBILITY = { public: 0.2, limited: 0.6, private: 1 } as const;
const PRICE_BASIS: Record<PriceType, number | null> = { quote: 1, benchmark: 0.6, assumption: 0.3, none: null };
const TARGET_MARGIN = 0.20; // a 20% gross margin or better scores 1 on economic_quality

/** Ordering vector for a route that is not blocked. Returns null for INELIGIBLE, MISMATCH and STOPPED, and when the
 *  evaluation belongs to another route. A component whose inputs are missing is null and is left out of the sum. */
export function priority(route: OpportunityRoute, evaluation: Evaluation): Priority | null {
  if (isBlocked(evaluation.state) || evaluation.route_id !== route.id) return null;
  const now = parseTime(route.time.now, false);
  if (now === null) return null;
  const mand = route.supply.requirements.filter((r) => r.mandatory);
  const base = String(route.supply.supplier || "").trim() ? FIT_BASE[route.supply.technical_fit] : null;
  const fit = base === null ? null : base * (mand.length ? mand.filter((r) => r.status === "verified").length / mand.length : 1);
  const vis = route.demand.visibility;
  const information_edge = vis ? VISIBILITY[vis] : null;
  const ev = evidenceView(route.evidence, now);
  const famScore = [0, 0.5, 0.8, 1][Math.min(ev.families.length, 3)];
  const evidence = route.evidence.length ? (ev.live_contradicted.length ? famScore / 2 : famScore) : null;
  const lead = num(route.time.lead_time_days), delivery = parseTime(route.demand.delivery_by);
  const window = delivery === null ? null : (delivery - now) / DAY;
  const execution = lead === null || window === null || window <= 0 ? null : clamp((window - lead) / window);
  const eco = evaluation.economics, basis = eco.quote_live === false ? PRICE_BASIS.assumption : PRICE_BASIS[eco.price_type];
  const economic_quality = eco.margin_pct === null || basis === null ? null
    : clamp(eco.margin_pct / TARGET_MARGIN) * basis * (eco.funding_headroom !== null && eco.funding_headroom < 0 ? 0.5 : 1);
  const d = evaluation.days_left;
  const time_value = d === null ? null : d < 0 ? 0 : d <= 7 ? 0.4 : d <= 45 ? 1 : d <= 120 ? 0.7 : 0.4;
  const c: Record<Component, number | null> = { fit, information_edge, evidence, execution, economic_quality, time_value };
  const keys = Object.keys(WEIGHTS) as Component[];
  const knownKeys = keys.filter((k) => c[k] !== null);
  const weighted_sum = Math.round(knownKeys.reduce((s, k) => s + WEIGHTS[k] * (c[k] as number), 0) * 1e6) / 1e6;
  return { ...c, known: knownKeys.length, weighted_sum, weights_version: WEIGHTS_VERSION };
}

// Sort order: state first, then the weighted sum over known components. Blocked states sort last whatever the inputs.
export const STATE_RANK: Record<RouteState, number> = { ACTIVE: 0, READY_FOR_AUTHORIZED_CONTACT: 1, READY_FOR_OWNER_REVIEW: 2, NEEDS_EVIDENCE: 3,
  RESEARCH: 4, MONITOR: 5, MISMATCH: 6, INELIGIBLE: 7, STOPPED: 8 };
export type Ranked = { route: OpportunityRoute; evaluation: Evaluation; priority: Priority | null };
export function rankRoutes(routes: OpportunityRoute[]): Ranked[] {
  return routes.map((route) => { const evaluation = evaluateRoute(route); return { route, evaluation, priority: priority(route, evaluation) }; })
    .sort((x, y) => STATE_RANK[x.evaluation.state] - STATE_RANK[y.evaluation.state]
      || (y.priority?.weighted_sum ?? -1) - (x.priority?.weighted_sum ?? -1) || (y.priority?.known ?? 0) - (x.priority?.known ?? 0) || cmp(x.route.id, y.route.id));
}
