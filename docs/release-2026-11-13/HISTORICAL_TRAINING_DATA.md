# Historical learning (F11): what data exists and what is built

Code: `dealdesk/lib/outcomes.ts`, `dealdesk/lib/comparables.ts`.
Tests: `dealdesk/tests/outcomes.test.ts` (47 checks), `dealdesk/tests/comparables.test.ts` (22 checks), run by `npm test`.
Status on 11 Nov 2026: pure TypeScript modules with tests. Nothing calls them yet: no page, no agent tool, and no
production store behind the ledger (tests use the in-memory store).

## The honest starting point

The system holds no first-party closed deals and no outcome data. Nothing in this release creates any, trains any
model or shows any probability. What can be shown today is descriptive public award history, labelled as such.

## The three corpora

| | Corpus | What it is | State today | What it may be used for |
|---|---|---|---|---|
| A | Public awards | Award notices from public sources (the same rows `leads/footprints.py` reads): date, title, value, country, buyer, winners | Exists (footprints cover 388,965 companies) | Description only: who won what, where, when, for how much |
| B | Consented first-party cases | Past deals of Sinder or of a client, handed over with written permission | None exist | Nothing until some exist and their rights are recorded |
| C | New operating outcomes | Events recorded in the ledger as the desk works | Empty; recording starts when the ledger is wired to a store | Later evaluation, once there is enough of it |

A public award says another company won a contract. It never says Sinder won, lost or was even involved, so corpus A
is never a label for our own results.

## What the ledger records (`lib/outcomes.ts`)

One event per verified step of a case, in funnel order: signal_found, need_confirmed, technical_match,
rfq_authorized, rfq_sent, rfq_responded, quote_received, proposal_delivered, negotiation_advanced, contract_signed,
delivered_invoiced, cash_collected; and two endings: lost, abandoned.

Each event carries: case_id, route_id, workspace, at (when it happened), actor, counterparty, proof, rights_scope
(own, client_confidential, public), model_version ("none" for a manual event), display_rank (the list position
shown to the user, or null) and, for lost and abandoned, a reason from a fixed list of twelve.

Rules the code enforces:

- No proof, no event. Proof is a source id, message id or document id. An unproven event is rejected on entry and
  ignored when a status is read.
- Lost needs a recorded lost event. Silence is not a loss.
- `caseStatus(events, now, followUpDays)` returns the furthest verified stage and a label:
  - never contacted: `not_contacted` (unknown, not negative), however old the case is;
  - RFQ sent, inside the follow-up window: `pending`; after it: `no_response_censored` (still not negative);
  - a reply or anything later: the stage reached;
  - `lost` or `abandoned` only from their own events; a later verified reply reopens the case.
- A public award cannot be recorded as contract_signed or as any other first-party step, and is ignored if passed in.
- `snapshot(events, asOf)` gives the point-in-time view. `assertNoLeakage(features, asOf)` throws when a feature was
  observed after asOf or has no observation date. The specification fixture is in the tests: a 2023 award backtested
  with earlier observations passes; the supplier's 2024 win or a 2025 e-mail reply makes it fail.
- Rights: a workspace sees all of its own events and, from other workspaces, only public ones.
  `exportForLearning(workspace)` returns own and public rows only. `pooledExport()` returns public rows only.
  Client-confidential events appear in no export and in no other workspace.
- The module never reads the clock; the caller passes `now`.

## What comparables return (`lib/comparables.ts`)

`comparableAwards(query, rows, asOf)` takes product or category words, country, buyer and period, and returns the
matching public awards with the reason each matched, counts by year and by winner, and the value range (min, median,
max) with n. Every result carries the statement "public award history, not Sinder outcomes".

- Awards published after asOf, and awards with no date, are excluded and counted.
- Two notices of one award (same buyer, same normalised title, same date) count once.
- Fewer than five awards with a stated value: rows are returned, no median.
- Values are USD as stated by the feed; no currency conversion happens here.
- Matching is by words in the title and exact country; it is a filter, not a similarity model.

## Deliberately not built

- No ranker and no learned ordering of opportunities.
- No calibrated probabilities, no "win chance", no score derived from history.
- No fine-tuning and no model trained on awards, messages or client data.
- No backfilled or synthetic outcomes. Test fixtures are synthetic and live only in the test files.
- No inference of our outcome from public data (a competitor's award is not our loss).

Reason: with zero labelled first-party outcomes any such number would be invented. Public awards carry heavy
selection (only winners are published, not bidders or prices offered) and say nothing about Sinder's own conversion.

## When a small tabular ranker could be considered

All of these, not some:

1. Volume: at least a few hundred cases in corpus C that reached rfq_sent, with at least about 50 verified positive
   outcomes at the stage being predicted and a comparable number of recorded losses. The exact threshold is a
   judgement to be set by the owner with a statistician; it is not derived here.
2. Every training feature has an observation date and passes `assertNoLeakage` at the decision time of its case.
3. Evaluation is split by time (train on earlier cases, test on later ones), never at random.
4. Censored cases (`pending`, `no_response_censored`, `not_contacted`) are treated as unknown, not as negatives.
5. display_rank and model_version are present, so the effect of what was shown first can be separated from merit.
6. Only rows from `exportForLearning` are used; client-confidential data needs separate written consent.
7. The ranker beats the current deterministic ordering on held-out later cases, and any probability shown is
   checked for calibration first. Until then the output stays an ordering with reasons, not a percentage.
8. The gates of the decision engine (`DECISION_ENGINE.md`) keep running before any ranking.

## Open items

- A persistent, append-only store for the ledger, and the calls that write events from outreach and deal state.
- A page or agent tool that shows comparables with their statement.
- Notices of one award that differ in date or buyer spelling across portals are not merged by the current key.
- Company names are grouped by normalised name only; that is not full entity resolution.
