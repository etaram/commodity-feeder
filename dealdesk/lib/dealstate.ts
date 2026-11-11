// Deal readiness gates (skill: sinder-deal-orchestrator, scripts/deal_state.py), on the deal builder's own records.
// research -> ready_for_rfq -> quoted -> reviewed. Each gate lists what is missing; passing a gate is data validation
// only. It never grants permission to send, bid or commit: that stays a human decision in the system.
import type { DealRecord } from "@/lib/deal";
import type { RouteRow } from "@/lib/routes";

export const GATES = ["research", "ready_for_rfq", "quoted", "reviewed"] as const;
export type Gate = (typeof GATES)[number];
export type Readiness = { reached: Gate | ""; next: Gate | ""; missing: string[]; validation_only: true; execution_approved: false };

const EMAIL = /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i, PHONE = /^\+[1-9][0-9]{6,14}$/, FORM = /^https?:\/\/[^\s/@]+\.[a-z]{2,}/i;
const live = (r: DealRecord[]) => {
  const latest = new Map<string, DealRecord>();
  for (const x of r) { const k = `${x.kind}|${x.record_id}`; const p = latest.get(k); if (!p || x.version >= p.version) latest.set(k, x); }
  return [...latest.values()].filter((x) => x.status !== "deleted");
};

/** A supplier party with a usable, structurally valid channel and a stated source (a contact page, a document, a notice). */
export function usableSupplier(d: Record<string, unknown>): boolean {
  const ph = String(d.phone || "").replace(/[\s().-]/g, "");
  const chan = EMAIL.test(String(d.email || "")) || PHONE.test(ph) || FORM.test(String(d.website || ""));
  return d.role === "supplier" && d.status !== "dropped" && chan && !!String(d.source || "").trim();
}

export function readiness(records: DealRecord[], routes: RouteRow[], today = new Date().toISOString().slice(0, 10)): Readiness {
  const r = live(records);
  const reqs = r.filter((x) => x.kind === "requirement"), parties = r.filter((x) => x.kind === "party"), quotes = r.filter((x) => x.kind === "quote");
  const econ = r.find((x) => x.kind === "economics"), stage = r.find((x) => x.kind === "stage");
  const gaps: Record<Gate, string[]> = { research: [], ready_for_rfq: [], quoted: [], reviewed: [] };
  if (!reqs.length) gaps.research.push("no requirement recorded (product, grade, quantity, standard)");
  if (!parties.some((p) => usableSupplier(p.data))) gaps.ready_for_rfq.push("no supplier with a sourced match and a valid contact channel");
  if (!routes.some((x) => x.verdict === "supported" || x.verdict === "conditional")) gaps.ready_for_rfq.push("no feasible entry route");
  if (reqs.some((x) => x.data.mandatory && x.data.status === "not_met")) gaps.ready_for_rfq.push("a mandatory requirement is not met");
  const actual = quotes.filter((q) => q.data.availability === "confirmed" && q.data.source_ref && (!q.data.valid_until || String(q.data.valid_until) >= today));
  if (!actual.length) gaps.quoted.push("no current, documented actual offer (indicative prices and directory data do not count)");
  if (!econ || !Number(econ.data.sale_price)) gaps.reviewed.push("economics not set on the offer");
  if (!stage || !["offer", "negotiation", "won"].includes(String(stage.data.stage))) gaps.reviewed.push("the evidence review is not recorded (stage offer or later)");
  let reached: Gate | "" = "";
  const missing: string[] = [];
  for (const g of GATES) {
    if (gaps[g].length) { missing.push(...gaps[g]); break; }
    reached = g;
  }
  const next = reached === "" ? "research" : (GATES[GATES.indexOf(reached as Gate) + 1] || "") as Gate | "";
  return { reached, next, missing, validation_only: true, execution_approved: false };
}

/** Provenance of one economics input: "quote" (a supplier quote recorded on the deal), "benchmark" (a dated public
 *  price), "confirmed" (a value the owner stated) or "assumption" (a default, or a value nobody confirmed). A default
 *  is never presented as a finding: a result that rests on at least one assumption or benchmark is a scenario. */
export type Basis = "quote" | "benchmark" | "confirmed" | "assumption";
export type EconInput = { value: number; basis: Basis; note?: string };
export const ECON_DEFAULTS: Record<string, number> = { freight: 0, other_costs: 0, fin_rate_pct: 10, supplier_pay_day: 0, customer_pay_day: 60 };
export const SCENARIO = "Scenario estimate", FROM_QUOTES = "Estimate from quotes";
export function econInputs(x: Record<string, unknown>, claims: Record<string, unknown> = {}, hasQuote = false): Record<string, EconInput> {
  const out: Record<string, EconInput> = {};
  for (const k of ["sale_price", "cost_goods", ...Object.keys(ECON_DEFAULTS)]) {
    const given = x[k] != null && x[k] !== "" && Number.isFinite(Number(x[k]));
    if (!given) { out[k] = { value: ECON_DEFAULTS[k] ?? 0, basis: "assumption", note: "default, not given" }; continue; }
    const c = String(claims[k] || "");
    if (c === "quote" && !hasQuote) out[k] = { value: Number(x[k]), basis: "assumption", note: "no quote is recorded on this deal" };
    else if (c === "quote" || c === "benchmark" || c === "confirmed") out[k] = { value: Number(x[k]), basis: c };
    else out[k] = { value: Number(x[k]), basis: "assumption", note: "no basis stated" };
  }
  return out;
}
export const econTitle = (inputs: Record<string, EconInput>) => Object.values(inputs).every((i) => i.basis === "quote" || i.basis === "confirmed") ? FROM_QUOTES : SCENARIO;

/** Deal economics in the stated model of sinder-deal-economics: daily simple interest on a negative balance,
 *  peak funding including accrued financing, a supplied funding limit and the warnings the skill requires. */
export type CashEvent = { day: number; amount: number };
export function cashCheck(events: CashEvent[], annualRate: number, fundingLimit: number | null) {
  const byDay = new Map<number, number>();
  for (const e of events) byDay.set(e.day, (byDay.get(e.day) || 0) + e.amount);
  const days = [...byDay.keys()].sort((a, b) => a - b);
  let cash = 0, interest = 0, peak = 0, prev = days[0] ?? 0;
  for (const d of days) {
    const charge = Math.max(-cash, 0) * annualRate * (d - prev) / 365;
    cash -= charge; interest += charge; peak = Math.max(peak, -cash);
    cash += byDay.get(d) || 0; peak = Math.max(peak, -cash); prev = d;
  }
  const warnings: string[] = [];
  if (cash < 0) warnings.push("final cash stays negative: settlement or funding unresolved");
  const capacity = fundingLimit == null ? "unknown" : peak <= fundingLimit ? "within the stated limit" : "exceeds the stated limit";
  if (fundingLimit != null && peak > fundingLimit) warnings.push(`peak funding ${Math.round(peak)} exceeds the limit ${Math.round(fundingLimit)}`);
  return { finance_cost: interest, peak_funding: peak, closing_cash: cash, funding_capacity: capacity, warnings };
}
