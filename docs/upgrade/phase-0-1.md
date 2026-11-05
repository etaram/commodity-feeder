# Deal Desk upgrade: phases 0 and 1

Spec: the upgrade brief of 5 November 2026. This file records what exists, what was reproduced, what changed, how it is measured and how to roll back. Facts are marked **observed** (read in code or data), **reproduced** (shown by a test or a run) or **suspected** (not yet shown).

## Phase 0: inventory (observed)

| Area | Where | State |
|---|---|---|
| Collection | `leads/*.py` per source, `.github/workflows/leads.yml` (2-hourly light, 04:40/16:40 heavy), `suppliers.yml` (01:40/13:40) | working; source health is "the job ran", not freshness or coverage |
| Normalisation, entity resolution | `leads/universe.py` (`norm()` name key + country), `leads/contacts.py` | working; one key per name+country, no legal-id merge across names |
| Product / sector classification | `leads/sectors.py` (CPV, UNSPSC, keywords), `leads/taxonomy.py` (commodity groups), `universe.main_sectors()` | partial; generic CPV codes decide material (PE pipe as steel, reproduced) |
| Evidence storage | supplier rows carry `sources`, `example_award`, `supplied`, `sector_why`; tenders carry `source`, `link` | partial; no assertion table with dates and status |
| Supplier search | `dealdesk/lib/panel.ts` `supplierSearch()`, index `data/web/suppliers.enc` (234,645 rows) | rewritten in phase 1 (below) |
| World / project intelligence | `leads/briefing.py`, `news`, `plays`, `dealdesk/lib/brief.ts` (daily brief, geopolitics) | working; no structured events or timelines |
| Opportunity generation | `leads/brain.py` (EV, route, margins, decision), `leads/dealfit.py` (rank) | working; defects listed below |
| Logistics, financing | `data/logistics`, `data/finance`, `lib/logistics.ts`, `lib/finance.ts` | directory matching by region and sector; no lane or eligibility evidence |
| Deal builder | `lib/deal.ts`, `app/api/panel/deal` (parties, stages, pipeline) | working |
| Auth, roles | `lib/gate.ts` (viewer / analyst / admin), session cookie | single organisation; no workspace model |
| Model usage | `lib/anthropic.ts` (Haiku default): query expansion, briefs, research jobs, reverse engineering | no per-job budget or cost log |

Baseline commit for measurement: `ba2448df7bde1825bf8911bd8c17bb54d16a494c`.

## Failures from section 4

| Case | Cause found | Status |
|---|---|---|
| A white maize: Corning, Cornerstone | **reproduced in code**: `stemRe` matched a term only at its left edge, so "corn" matched "corning"; the company name counted as product evidence | fixed: whole-word terms; name never establishes capability |
| B urea cream in a fertilizer search | **reproduced**: no product-form distinction | fixed: urea family rules (cosmetic, peroxide incompatible; resin, AdBlue related) |
| C food company with reefer genset | **reproduced**: contract and shipment wording counted like product evidence | fixed: transport-context rule; evidence ranked own description > contract items > customs headings > name |
| D hot rolled coil: cold rolled, wire rod, shoes | **reproduced**: HS codes counted as own evidence; no specification check | fixed: HS is a retrieval signal (plausible at most); hot-rolled family rules |
| E power transformer: instrument transformers, EPC, duplicates | **reproduced**: no role or type distinction; no dedupe | fixed: instrument / accessory / execution-role rules; dedupe by normalised name + country |
| F Scottish Water PE pipes as iron & steel | **reproduced**: CPV 4416 (pipes) is mapped to the steel group regardless of material | fixed: `taxonomy.refine_group()`; the title's material decides |
| G Fertiglobe: plausible but not engagement-ready | observed: match and readiness were one signal | partly: gaps (website, role) are listed per result; readiness checks (legal id, verified contact, capacity) are phase 2 |
| H 49/49 sources healthy | observed: health = job success | open: freshness, parse completeness, duplicate rate are phase 2 |

## Phase 1: what changed

**Supplier matching** (`dealdesk/lib/supmatch.ts`, used by `supplierSearch`):
- Stage B: whole-word, whole-phrase terms; customs codes and contract titles retrieve, they do not prove.
- Stage C: every result is `supported`, `plausible`, `related` or `incompatible` (dropped), with the evidence field that decided it, the conflicts and the gaps.
- Stage D: order is bucket, then evidence strength, then score; tier never lifts a mismatch; maker before trader only as a tie-break, and a role filter (all / manufacturers / traders) replaces the forced grouping.
- Stage E: the research screen groups by bucket and shows "fits because...", conflicts and what is missing.
- Each row carries `match_version` (`match-1`).

**dealfit.py** (section 12), each checked in `tests/test_dealfit.py`:
- "not open to foreign bidders" no longer reads as open; an explicit restriction beats an IFI mention (route kept, flagged).
- unknown goods share counts half and is flagged (was full).
- NaN or infinite inputs become unknown (min(100, nan) was 100).
- expired notices score 0.
- a false or "candidate" partner value is not a partner.
- profile weights no longer apply twice to EV.
- `base_score` survives repeated runs; warnings are no longer truncated.
- "plasma cutting", "blood pressure monitor" are not licensed medicines.
- the comment claiming Ignore can never outrank Pursue was false; `fit_bucket` (1 Pursue, 2 Watch, 3 Ignore) now gives strict ordering where it is needed.

Not changed (recorded): broad sector supplier counts still feed the score (needs exact-capability counts, phase 2); EV definitions in `brain.py` are not yet unified.

## Measurement

- `dealdesk/tests/supmatch.test.ts`: 17 cases from A-F, all pass.
- `tests/test_dealfit.py`: 9 checks, all pass.
- `.github/workflows/supplier-eval.yml`: runs the live search code on the real index for 38 queries, current and baseline, no model calls, and writes the private tab **Search eval** (top 15 per query, bucket, evidence, conflicts, gaps, baseline at the same rank). The `label` column is for human review (yes / no / related); precision@5 and @10 are computed only from reviewed rows and show the sample size. No precision number is claimed before labels exist.

## Rollback

- Code: revert the phase-1 commit; `supmatch.ts` is additive and `supplierSearch` returns the old columns plus new ones, so callers that ignore the new columns are unaffected.
- Data: no data migration; the supplier index and tenders are rebuilt by the scheduled workflows.
- Search tuning switch: `SUPPLIER_STRICT=off` and `SUPPLIER_EXPAND=off` (existing environment flags).

## Measured on 5 November 2026 (web-verified sample)

181 top-5 results of 38 queries were checked by three independent model reviewers against official or authoritative sources (company sites, regulators, filings, tender awards). This is a model adjudication with new evidence, not a human one; 56 rows stayed unknown (23 of them never checked because the shared search budget ran out). The 125 decided facts are stored in the private tab **Verified capabilities** and reused by the live search for a year.

| Version | 'supported' results that can supply | 95% interval |
|---|---|---|
| match-1.1 (before the review) | 84 of 115 (73%) | +/-8% |
| match-1.2 (rules from the review) | 54 of 67 (81%) | +/-9% |

Caveats: the rules for 1.2 were derived from the same labels they are measured on, so 81% is optimistic (confirmed below); a held-out set is needed before claiming the 90% gate. The benchmark runs without the AI query expansion the live app uses.

What the review taught (now rules): processed forms (flour for wheat, degermed corn, date syrup, coconut sugar, specialty cement); equipment made for the product or that uses it (ammunition lines, LPG engines, ammonia fuel cells, battery testers, excavator attachments, bitumen boards); EPC and installers; forwarders; procurement intermediaries; shipment records that name cargo, not a catalogue.

## Phase 2 started

- `leads/source_quality.py`: per source freshness, parse completeness, duplicates, mirrored notices, expired notices still listed, share useful to Sinder; shown on the status page next to delivery. First run: 71 of 132 notice sources flagged; about 6,000 expired notices were listed as open (now left out of the open list at each merge).
- Supplier page: an engagement-readiness checklist (legal identity, official site, reachable channel, product fit, export evidence, role), separate from the match.

## Phase 3 started: workspaces (5 November 2026)

- `lib/auth.ts`: the signed session carries a workspace id (`ws`); legacy tokens and the bootstrap login belong to the original workspace (`sinder`). Ids are validated (`asWs`).
- `lib/gate.ts`: every gated request re-reads role, status and workspace from the Users tab (cached 30 s), so a disabled account or a lowered role takes effect at once, not after the 30-day token expires.
- `lib/scope.ts`: deny-by-default list of public collections; the original workspace's private tabs (BD, key accounts, intel, pursuits, jobs, contacts, projects, tasks, approvals, attention) are not served to, or writable by, another workspace (`/api/panel/get`, `/api/panel/append`).
- Deals (`lib/deal.ts`): rows carry the workspace in column K; reads filter by it (legacy rows stay with the original); a guessed deal id from another workspace returns nothing.
- The private network (`/api/panel/know`) is served only to the original workspace.
- Users admin: an admin sees and changes only its own workspace's accounts; only the original workspace can move an account.
- Sheets: `Users!M` and `Deal Records!K` columns added (header `workspace`).
- Tests: `dealdesk/tests/scope.test.ts` (9 isolation checks, all pass).

Not yet: per-workspace strategy (partners, margins and the dealfit preferences are still the original workspace's and are computed once for the shared tender list), client dossiers, saved views. Rollback: revert the commit; blank workspace columns read as the original workspace, so no data migration is needed either way.

## Held-out check (5 November 2026)

89 results the rules had never seen (ranks up to 10, not in the first sample), checked the same way; 68 decided.

| Evidence behind a 'supported' result (match-1.2) | Can supply |
|---|---|
| the company's own product description | 17 of 20 (85%) |
| a public contract it won | 14 of 27 (52%) |
| all 'supported' | 31 of 47 (66%, +/-14%) |

So the 81% did not hold on unseen data. The cause is clear in the split: contract winners are often contractors, installers or distributors. match-1.3 keeps 'supported' for own-description evidence only and moves contract-only evidence to 'plausible' (ranked after shipment records). On this held-out sample that rule gives 17 of 20 (85%, +/-16%, small sample); not yet at the 90% gate. The 68 facts were added to Verified capabilities (194 rows in all).
