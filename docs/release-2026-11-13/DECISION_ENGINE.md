# Decision engine: the deterministic core of the Trade Brain

Code: `dealdesk/lib/route.ts`. Tests: `dealdesk/tests/route.test.ts` (80 checks, run by `npm test`).
Status on 11 Nov 2026: a pure TypeScript module with tests, read by one deal-page card through one read-only
endpoint. See "Wired" below for exactly what is connected.

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
- No persistence of routes or evaluations: the route state is computed on each read and not stored.
- One route per deal only (see "Wired"); several routes for one demand are not built or ranked in the product.
- No calibrated probabilities. No win likelihood and no expected value.
- No source-family detection, no sanctions screening (the alert is an input flag), no cash-flow model beyond
  one capital-need figure, no currency conversion, no multi-supplier comparison inside one route.

## Wired (11 Nov 2026, branch release/wire)

Connected:

- `lib/routemap.ts`: `routeFromDeal(records, comparison, now, ctx)` builds one route from a deal's saved records.
  Tests: `tests/routemap.test.ts`.
- `GET /api/deal/route-state?id=DEAL` (analyst or admin; workspace from the session): reads the deal records and
  the quote comparison, looks the id up in the tender index, and returns `{ evaluation, priority, next_task }`
  plus the supplier choice and the send-policy line. Read only: no model call, nothing stored, nothing sent.
- `lib/missionstore-sheets.ts`: the mission store on the tab "Missions" (append-only; columns time, workspace,
  mission_id, kind, id, rev, status, data). "Missions" is in `STATE_TABS`, so it lands in the state sheet when
  `STATE_SHEET_ID` is set. The tab is not created at import or on read; the first append creates it, hidden.
  Reads return one workspace's rows by exact match. Tests: `tests/missionstore.test.ts`.
- `GET /api/missions[?deal_id=]` lists the workspace's missions. `POST /api/missions` records a mission (type,
  goal, deal_id, cost budget up to 1,000 USD; analyst or admin). The audit session can read both and cannot post.
- The React deal page (`app/deal/[id]`, `components/RouteState.tsx`) shows a "Route state" card and a "Missions"
  list with a create form. `public/panel.html` is unchanged.

How a deal file becomes a route (anything not listed is null or "unknown"):

| Route field | Taken from |
|-------------|-----------|
| route type | economics record role: agent gives `agency`, otherwise `principal_trade` |
| represented organisation | the session's workspace |
| supplier | the one selected supplier party; else the only quoting supplier; else the only supplier party; several candidates and none selected gives none |
| requirements | requirement records: met = verified, not_met = contradicted, unknown or missing = unknown |
| technical fit | `supported` only when a supplier is chosen and every mandatory requirement is met; otherwise `unknown` |
| data rights, representation | requirement records named "Legal: data rights" and "Legal: representation" (met = yes, not_met = no, absent = not checked) |
| demand status, buyer deadline | the tender index entry with the deal's id (planned, tender = open, awarded, closed); without one, stage won = awarded, lost = closed, else unknown |
| route deadline | the stage record's deadline |
| quantity, lead time, quote validity | the chosen supplier's latest quote |
| price basis | `quote` when that quote has a price; `assumption` when only the economics record has a cost; else `none` |
| sale price, funding limit | economics record |
| cost | economics record: goods plus stated freight, insurance and inspection (not those marked as inside the quote). Percentage items (duty, bank, financing, commission, contingency) are not applied |
| evidence | the tender notice (official-source-asserted, family = the notice's host) and the chosen quote's source (counterparty-confirmed when availability is confirmed, otherwise client-asserted; family = the supplier) |
| owner mandate | `per_message` when a party record carries the note the deal agent writes after the owner approved a message; otherwise `none`. Never `conversation` |
| engagement | `in_contact` when the chosen supplier's party status is contacted, replied, quoted or selected |

Never in a deal file, so always unknown to the card: capital need (so `profit_statement` is always "blocked"),
demand visibility, required delivery date. `sanctions_alert` is always false because no screening result is
stored on a deal: the card says sanctions are not screened here. It does not mean "screened and clear".

Not connected:

- No mission task is added, reserved, run or reviewed anywhere in the product. No model call. Creating a mission
  writes one row and one activity-log line.
- `mandate.decideSend` is not part of any sending path. `lib/dealagent.ts`, the outbox and per-message approval
  are unchanged. `routemap.contactPolicy()` calls `decideSend` with no mandate and conversation mode off, only to
  print "Contact needs owner approval" on the card.
- No mandate store on Sheets, no way to create or approve a conversation mandate in the product.
- The route state is not shown in `panel.html`, Telegram or the daily brief, and does not gate any action.
- The live sheet was not touched from this branch: whether a "Missions" tab already exists there is not checked.

Mapping decisions that need the owner's confirmation:

- All mandatory requirements met reads as fit `supported`, although requirement evidence is recorded per deal,
  not per supplier.
- Legal checks are recorded as two specially named requirements. Until both exist, every deal is in RESEARCH and
  its first task is the data-rights question.
- One past owner-approved message makes the mandate `per_message` for the whole deal.
- A deal that is not in the tender index has no field for demand status and stays in RESEARCH unless its stage is
  won or lost.
