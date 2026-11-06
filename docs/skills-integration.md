# Deal agent skills: integration map (6 Nov 2026)

The 9 skills in `.claude/skills/` are mapped to the code that already does the work. A skill never adds sending,
bidding or commitments: those stay human decisions (outreach sending is off).

| Skill | Adapter in the system | Status |
|---|---|---|
| sinder-supplier-matching | `dealdesk/lib/supmatch.ts` (supported / plausible / related / incompatible), `leads/workflow_demo.py` with `match_guard.py` | RO and maize-color families added (match-1.4) |
| sinder-tender-route | `dealdesk/lib/routes.ts`: one row per route (direct, agency, local partner, sub-supply), GPA basis for Israel | new; shown in the deal workspace |
| sinder-deal-orchestrator | `dealdesk/lib/dealstate.ts` gates research / ready_for_rfq / quoted / reviewed on `Deal Records` | new; `/api/deal` GET, `DEAL_GATES=off` rolls back |
| sinder-deal-economics | panel `ECON.deal` cash ledger + `cashCheck` (funding limit, final negative cash) | funding limit field and warnings added |
| sinder-execution-options | finance and logistics directories (`leads/refine_modules.py`), partner ladder in `lib/deal.ts` | existing |
| sinder-evidence-review | assertions ledger, `Registry checks`, refine conflicts | existing |
| sinder-market-intelligence | daily brief, geopolitics, `lib/intel` events and project timelines | existing |
| sinder-data-refinement | `leads/refine.py`, `refine_modules.py`, `company_check.py`, `registry_check.py`, `archive.py`, `validate.py` | running hourly |
| sinder-client-development | tenders and buyers by need (`workflow_demo.py` part C), outreach drafts (sending off) | sandbox only |

Missing adapters: the tender document reader does not yet extract eligibility clauses into `access`, so most notices
give "unknown" for the direct route; a contact finder pass for the supported matches that have no channel; a
department check on e-mails (a sponsorship or marketing mailbox is not a sales channel).
