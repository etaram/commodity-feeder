# Capability matrix - baseline 11 Nov 2026

Status words: WORKING (tests or live use prove it), PARTIAL (code exists, gaps listed), BROKEN, ABSENT, UNVERIFIED (code
exists, not exercised in this pass). Evidence is a file path or a command run in this pass. Baseline commit: a0a60701.

Commands run: `cd dealdesk && npm test` (14 files, all pass after the fixes below), `npx tsc --noEmit` (exit 0),
GitHub Actions run history for the last 7 days (539 runs).

| Area | Status | Evidence | Gap against the release spec |
|---|---|---|---|
| Intelligence feed: tenders, awards, suppliers, prices, search | WORKING | app/tenders, app/suppliers, app/prices, app/explore; tests/search.test.ts, supmatch.test.ts | Live route timing and mobile pass not re-run in this pass (F01, F20) |
| Collectors and indexes | WORKING | 30 workflow files; 7-day history: 4 failed runs in 539, the rest success or cancelled by concurrency | Per-source status page for the owner (F19) is PARTIAL: coverage board exists (leads/coverage_board.py) |
| Scheduler ("heartbeat") | WORKING, wasteful | .github/workflows/heartbeat.yml: a sleep loop that only starts overdue workflows; 47% of runner minutes | Replace with a plain timer on the server |
| Client workspace: create, upload, extract, review | PARTIAL | app/api/clients/*, lib/dossier.ts, lib/docextract.ts (PPTX, PDF text layer), tests/dossier.test.ts (78 checks) | No DOCX/XLSX price book; no OCR; no client-facing portal page; no representation-mandate record (F02, F03) |
| Client BD mission | PARTIAL | app/api/clients/[id]/prospects, targets; lib/outreach/* | Not connected into one mission object with budget and steps (F04) |
| Deal file: quotes, economics, logistics, finance | PARTIAL | app/deal/[id], lib/deal.ts, lib/quotes.ts, lib/finance.ts, lib/logistics.ts; tests/dealstate.test.ts, econ.test.mjs | Spec fixture (USD 421.64 financing, funding-limit block) not yet a test (F12) |
| Deal agent with owner approval per message | WORKING in tests, never used on a real deal | lib/dealagent.ts; tests/dealagent.test.ts (23 checks) | The test had not been runnable since new tools were added; repaired in this pass |
| Outreach engine: outbox, idempotency key, suppression, kill switch, sender check | PARTIAL | lib/outreach/outbox.ts, suppression.ts, campaign.ts; tests/outreach.test.ts (104 checks) | `delivery_unknown` state after a provider timeout is ABSENT (F16); live channel not exercised |
| Conversation-level mandate | ABSENT | no "mandate" in app or lib | Per-message approval stays the only mode (F14 passes in that mode only) |
| Mission object (goal, steps, budget, stop rules) | ABSENT | "Agent Runs" tab holds single-agent runs only | Section 7 of the spec |
| Trade Brain: route states, gates before ranking | ABSENT as specified | lib/strategy.ts, lib/verdict.ts, lib/assertions.ts give parts (assertions, verdicts) | No OpportunityRoute object, no route state enum |
| Strategic OSINT: event to mechanism to route | PARTIAL | lib/intel.ts, lib/markets.ts, leads/events; tests/intel.test.ts | No causal-edge records, no scenario cards (F07, F08) |
| Historical outcome ledger and comparable cases | PARTIAL | data/web/footprints (388,965 companies from public awards), lib/researchmemory.ts | No outcome ledger, no point-in-time snapshots, no first-party cases exist (F11) |
| Model router: code, local, cloud | ABSENT | single provider in lib/anthropic.ts; no local model, no OpenAI adapter | Daily AI budget is an alert only, never a stop (lib/anthropic.ts line 44) |
| Workspace isolation | PARTIAL | lib/scope.ts, signed workspace in session; tests/scope.test.ts (11 checks) | Storage is one Google Sheet per function, not per tenant; adversarial tests for documents, cache and prompts missing (F17) |
| Authentication | PARTIAL | lib/auth.ts, middleware.ts; cookie httpOnly, secure, 30 days | Default signing secret removed in this pass. Still open: no login rate limit, shared team login still accepted, no MFA (F18) |
| Sheets formula injection | WORKING (fixed earlier) | lib/sheets.ts writes with valueInputOption=RAW everywhere | - |
| Public exposure | BROKEN against spec | repository is public; app reads data from public raw URLs; the home panel HTML is fetched from the public main branch at run time (app/route.ts) | Needs the server; DATA_BASE_URL switch already exists (lib/rawbase.ts) |
| PostgreSQL, Compose kit, Caddy | UNVERIFIED on a real server | deploy/*; local run verified earlier (login 200, MCP 9 tools) | No server bought; state still in Google Sheets |
| Backup and restore | ABSENT | no off-site backup, no restore test | F21 |
| Monitoring for the owner | PARTIAL | app/ops, app/integrity, /api/health, watchdog workflow | No alerts for stale data or failed backup |
| Nine domain skills | WORKING as packaged skills | .claude/skills/* | Used by the assistant, not called by the production backend |

## Fixed in this pass

1. `npm test` did not exist; added tests/run-all.mjs so all 14 test files run with one command.
2. The deal agent approval test could not be built (JSON imports, stale mocks). Repaired; 23 checks pass.
3. Sign-in no longer falls back to a secret that is readable in the code when AUTH_SECRET is missing in production
   (lib/auth.ts, middleware.ts). Not yet deployed.

## Not checked in this pass

Git history scan for secrets, live production behaviour, mobile layout, Vercel plan terms, load on the candidate server.
