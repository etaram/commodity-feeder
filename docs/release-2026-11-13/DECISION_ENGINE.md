# Decision engine: the deterministic core of the Trade Brain

Code: `dealdesk/lib/route.ts`. Tests: `dealdesk/tests/route.test.ts` (80 checks, run by `npm test`).
Status on 11 Nov 2026: a pure TypeScript module with tests. Nothing calls it yet.

## What it does

One `OpportunityRoute` in, one state out. A route is one way for one represented organisation to act on one
demand with one supplier candidate. The same award can carry several routes (prime bid, supply to the winner,
EPC subcontract, agency, client business development, principal trade); each is evaluated alone.

`evaluateRoute(route)` returns `{ state, blockers[], missing[], reasons[], next_task }` plus a gate trace,
`exact_fit`, `source_families`, `independently_corroborated`, `days_left`, `profit_statement` and the computed
economics. The same input always gives the same output. The caller supplies `time.now`; the engine does not
read the clock and throws if `now` is unreadable.

## Gates (run in this order, before any ranking)

| # | Gate | Blocks with | Holds with |
|---|------|-------------|------------|
| 1 | access / legal | sanctions alert: STOPPED, "qualified review required", never cleared here. No data rights, no right to represent, no represented organisation: INELIGIBLE | a legal flag not checked (null): RESEARCH |
| 2 | technical fit | a contradicted mandatory requirement, or fit `incompatible`: MISMATCH | no supplier or fit `unknown`: RESEARCH. Unknown mandatory requirement, fit `plausible` or `related`: NEEDS_EVIDENCE |
| 3 | route eligibility | demand closed or cancelled; prime bid on an awarded demand: INELIGIBLE | demand status unknown: RESEARCH. Demand only announced, or supply-to-winner before the award: MONITOR |
| 4 | time | binding deadline passed; lead time cannot meet the delivery date: INELIGIBLE | prime bid with no deadline at all: RESEARCH |
| 5 | authority | owner stopped the route: STOPPED | no owner mandate: limit READY_FOR_OWNER_REVIEW |
| 6 | finance | never blocks the route | capital need over the funding limit: limit READY_FOR_OWNER_REVIEW |
| 7 | evidence | never decisive | no countable evidence, or a live contradicted claim: NEEDS_EVIDENCE. One source family: limit READY_FOR_OWNER_REVIEW |

How the state is chosen: the first decisive blocker in gate order wins; otherwise the first holding state in
gate order; otherwise READY_FOR_OWNER_REVIEW if any limit applies; otherwise READY_FOR_AUTHORIZED_CONTACT, or
ACTIVE when a person has recorded `engagement: "in_contact"`. No score is consulted at any point.

Rules worth knowing:

- Exact fit is claimed only when fit is `supported` and every mandatory requirement is `verified`.
- Time is computed from the dates. The buyer's published deadline (`demand.deadline`) binds `prime_bid` only;
  every route is bound by its own `time.deadline`. An expired prime bid and an eligible `supply_winner` route for
  the same award coexist. A date without a time runs to the end of that day (UTC).
- Without an owner mandate the state never exceeds READY_FOR_OWNER_REVIEW, whatever else is recorded.
- Finance numbers are nullable and stay null in the output: missing is never turned into zero, and a real zero
  stays zero. `profit_statement` is `authoritative` only with a live quote, a known sale price and cost, and a
  capital need inside a known funding limit. Missing finance does not stop research or contact (an RFQ is how a
  quote is obtained).
- Evidence counts by source family. Countable statuses: observed, official-source-asserted,
  independently-checked, counterparty-confirmed. Two items of one family count once, so a single family is not
  independent corroboration even when an item is marked independently-checked. client-asserted and inferred are
  listed in the reasons and never counted. Items past `valid_until`, `missing` and `superseded` are not counted.
- Input order of evidence and requirements does not change the result.

## States

| State | Meaning | Next task |
|-------|---------|-----------|
| STOPPED | sanctions alert or owner stop | none |
| INELIGIBLE | this route type cannot be used (legal, demand status, time) | none |
| MISMATCH | the supplier's evidence contradicts a mandatory requirement | none |
| NEEDS_EVIDENCE | a candidate exists; a requirement or a core claim is not evidenced | yes |
| RESEARCH | a structural input is missing (supplier, fit, legal check, demand status, deadline) | yes |
| MONITOR | valid route, nothing to do until an external event (publication, award) | yes |
| READY_FOR_OWNER_REVIEW | gates passed; the owner must approve or decide on a limit | none (approval pending) |
| READY_FOR_AUTHORIZED_CONTACT | gates passed, mandate held, two source families | none (decision reached) |
| ACTIVE | as above, and contact is recorded | none |

`nextTask(evaluation)` returns `{ kind, question, why }`: among the gaps that hold the route in its state, the
one with the lowest cost (1 = desk check, 5 = needs a counterparty), ties broken by gate order. The costs are
fixed constants in the code, not measurements.

## Priority vector

`priority(route, evaluation)` returns null for STOPPED, INELIGIBLE and MISMATCH, and for an evaluation of
another route. Otherwise six components, each 0..1 or null when its inputs are missing:

| Component | Weight | Built from |
|-----------|--------|-----------|
| fit | 0.20 | fit bucket times the share of mandatory requirements verified |
| information_edge | 0.20 | `demand.visibility` (public 0.2, limited 0.6, private 1.0) |
| evidence | 0.15 | source families (1: 0.5, 2: 0.8, 3 or more: 1.0), halved by a live contradiction |
| execution | 0.20 | slack between lead time and the delivery date |
| economic_quality | 0.15 | margin against a 20% target, scaled by price basis, halved over the funding limit |
| time_value | 0.10 | days to the deadline (step function, best between 8 and 45 days) |

Plus `known` (how many components are known), `weighted_sum` (over known components only, no renormalisation)
and `weights_version`. `rankRoutes` sorts by state first, then the weighted sum, then `known`, then id.

The weights and the component formulas are proposed management weights. They are not calibrated against
outcomes, and the weighted sum is an ordering aid, not a likelihood of winning or of anything else. Because the
sum is not renormalised, an unknown component adds nothing to the sum; the null stays visible in the vector.

## Reuse

`TechnicalFit` is the `Bucket` type of `lib/supmatch.ts` plus `unknown`. Funding capacity uses `cashCheck` from
`lib/dealstate.ts`. Neither file was changed. `lib/assertions.ts` detects mirrored sources from URLs and
document hashes; this engine takes `source_family` as given and does not call it.

## Decisions made here that need an owner's confirmation

- A single source family limits the route to owner review, including when a mandate is held.
- Fit `related` holds the route in NEEDS_EVIDENCE; it is not treated as a mismatch.
- A lead time longer than the time to delivery makes the route INELIGIBLE.
- The fields `demand.delivery_by`, `demand.visibility` and `authority.engagement` were added to the route type;
  ACTIVE and the owner stop cannot be expressed without `engagement`.

## Not implemented

- No model calls. Fit verdicts, requirement statuses and evidence statuses are inputs; nothing produces them here.
- No UI and no API route. No page, panel or endpoint uses the module.
- No persistence. Routes and evaluations are not stored, and no existing record is mapped to an
  `OpportunityRoute`.
- No calibrated probabilities. No win likelihood and no expected value.
- No source-family detection, no sanctions screening (the alert is an input flag), no cash-flow model beyond
  one capital-need figure, no currency conversion, no multi-supplier comparison inside one route.
