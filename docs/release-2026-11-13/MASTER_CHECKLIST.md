# Master checklist - Sinder Deal Desk release, gate Friday 13 Nov 2026

Status as of Wed 11 Nov 2026, 18:00 Israel time. Words used: DONE (a test or a live check proves it), PARTIAL (exists,
gap named), NOT STARTED, OWNER (waits for an owner action). The specification is MASTER_BUILD_SPEC_v2.md in this
folder. Evidence: CAPABILITY_MATRIX.md, RED_TEAM_2026-11-11.md, DECISION_ENGINE.md, CONVERSATION_MANDATES.md,
HISTORICAL_TRAINING_DATA.md, MODEL_ROUTING_AND_COSTS.md, and `cd dealdesk && npm test` (24 files, all pass).

## A. The 25 acceptance tests

| ID | Test | Status | What exists | What is missing |
|---|---|---|---|---|
| F01 | Intelligence feed | PARTIAL | Live and used daily; reads data from the private gateway | Mobile and load-time pass not re-run; source and time labels not audited |
| F02 | Client creation and upload | PARTIAL | API, PDF and PPTX extraction, claim review in code, 78 checks | No DOCX/XLSX; client screens not verified live; tenant-private file storage not proven |
| F03 | Membrane company example | NOT STARTED | Matching fixture for SWRO membranes (F09) | The client flow itself has not been run on a membrane deck |
| F04 | Client BD mission | NOT STARTED | Mission object and store; prospects and targets APIs | No mission runner; nothing dispatches specialist tasks |
| F05 | Tender mission | NOT STARTED | Deal agent does parts of it in one run | Not a mission with steps, budget and review |
| F06 | Award-winner mission | NOT STARTED | Winners feed, footprints, route state engine | Not a mission; remaining-need hypothesis not modelled |
| F07 | OSINT trade thesis | NOT STARTED | Events, markets, intel modules | No causal chain record, no scenario cards, no falsification test |
| F08 | Client-specific world context | NOT STARTED | - | Depends on F07 and the client workspace |
| F09 | Product mismatch | DONE | 34 checks; live | Live query expansion path not exercised by the fixture |
| F10 | Model router | PARTIAL | Local models measured on the server; decision recorded | No router module, no per-call tier/cost record, daily AI budget is an alert not a stop |
| F11 | Historical learning | PARTIAL | Outcome ledger and comparable awards, 69 checks | Nothing writes to the ledger; no award import into it; no persistent store |
| F12 | Economic calculator | DONE | Spec fixture passes; inputs labelled quote / benchmark / assumption; live | Peak funding includes accrued interest (spec states principal): definition to confirm |
| F13 | Bid / commit / payment limits | PARTIAL | Mandate engine denies sign, bid, pay in every mode; agent has no such tools | Prompt-injection fixture for an uploaded deck is not yet a test |
| F14 | Conversation approval | DONE (per-message mode) | Owner-only approval and agent start, live; 41 checks | Conversation mode is built and OFF; switching it on needs owner approval |
| F15 | Reply and escalation | PARTIAL | Reply classification, suppression, 104 outreach checks | Inbound reply matched to the right case not verified on a real channel |
| F16 | Outbox idempotency | DONE (in tests) | delivery_unknown, reconcile, duplicate key, 37 checks | Not exercised with a live provider |
| F17 | Tenant isolation | PARTIAL | Workspace in signed session, gate() everywhere reviewed, contact data owner-only | Adversarial tests for documents, cache, summaries, prompts; storage is shared sheets |
| F18 | Critical security | PARTIAL | No default secret; login limit; owner-only sending; audit key restricted; data served from a private gateway; 8 of 12 review findings closed | Repository still public; shared team login; register limiter in memory; upload and SSRF checks not reviewed; git history not scanned |
| F19 | Source integrity | PARTIAL | Coverage board; 4 failed runs in 539 last week | No owner-facing per-source status; "silent zero" case not tested |
| F20 | UI | NOT STARTED (as a test) | Pages exist in English and Hebrew | 360 px mobile pass, keyboard, both directions, inert buttons: not checked |
| F21 | Recovery | PARTIAL | Daily encrypted DB backup, restore test, copy to Google Drive, repo mirror on the server and on the owner's Mac | DB is nearly empty; no full restore of app plus data into a separate environment; key copy to the owner pending |
| F22 | Infrastructure load | NOT STARTED (as a test) | All workflows run on the server since 16:40 | First full collection run is slower than on GitHub: under observation; no backlog measurement yet |
| F23 | Budget | PARTIAL | Server USD 24/month, backups USD 0 | AI spend cap is an alert only |
| F24 | Audit and attribution | PARTIAL | Activity log, Outbox tab, approvals tab | Not every claim links to source and version; no append-only audit stream |
| F25 | Commercial demonstration | NOT STARTED | - | One real case from feed or deck to quote-ready dossier with a sandbox or approved outreach |

Count: 4 done, 13 partial, 8 not started. Friday status today: NOT READY.

## B. Specification sections outside the test table

| Section | Item | Status |
|---|---|---|
| 2 | Five-part navigation: Today, Discover, Missions, Deals, Clients | NOT STARTED (current navigation is the older panel) |
| 2 | Owner morning flow: max five decisions, what changed / why / evidence / next safest action | PARTIAL (today page and daily brief exist, not in this form) |
| 2 | Status vocabulary NOT_CHECKED / CHECKED_NO_ISSUE / FAILED / STALE / VERIFIED | NOT STARTED |
| 3 | Representation mandate record (rights, territories, sender, fee, expiry, training rights) | NOT STARTED |
| 3 | Client portal | NOT STARTED |
| 4 | Route states and gates before ranking | DONE in code, wired to the deal page; sanctions and capital need not fed from deal files |
| 4 | Evidence record with source family and validity | PARTIAL (assertions, evidenceFamilies) |
| 4 | Independent review of conclusions | PARTIAL (used in the build process; red_team role defined for missions, no runner) |
| 5 | Feedback reasons after each owner decision | NOT STARTED |
| 6 | Hard spend caps per task and per day; kill switch for paid AI | NOT STARTED (kill switch exists for outreach only) |
| 7 | Ten specialist roles mapped to personas | DONE (two roles have no persona: osint, red_team) |
| 7 | Mission runner (dispatch, retries, resume) | NOT STARTED |
| 8 | Agency / principal / BDaaS fee models in the economics engine | NOT STARTED (principal route only) |
| 8 | Logistics fit from real origin and destination | PARTIAL (logistics_options tool) |
| 9 | PostgreSQL as the operational store | PARTIAL (running, empty; app still writes to Google Sheets) |
| 9 | Private repository | OWNER + work: blocked by Vercel build source and the server sync job |
| 9 | Two-level kill switch (sends, paid AI) | PARTIAL |
| 10 | Official signal sources with licence and status tracking | NOT STARTED |
| 12 | Required documents in docs/release-2026-11-13 | 8 of 14 exist: missing ARCHITECTURE, CURRENT_STATE, DATA_CONTRACTS, RESEARCH_FRAMEWORKS, CLIENT_PORTAL_AND_PERMISSIONS, TEST_MATRIX (this file covers it), SECURITY_THREAT_MODEL, BACKUP_RESTORE_RUNBOOK, RELEASE_GATE_REPORT |

## C. Infrastructure migration

| Item | Status |
|---|---|
| Server bought and hardened (key-only SSH, firewall, fail2ban, only port 22 and the gateway open) | DONE |
| All workflows and the scheduler on the server; watchdog and audit-ui on GitHub | DONE |
| Site reads data from the private gateway | DONE (72 requests from Vercel observed) |
| Backups: encrypted, restore-tested, Google Drive | DONE |
| Gateway host name is 216-158-234-218.sslip.io (third-party name service) | PARTIAL: replace with data.sinder.pro (DNS is at IONOS, owner action) |
| Four 404 answers on the gateway | OPEN: identify the paths |
| First collection run on the server slower than on GitHub | OPEN: measure per source |
| Repository private | BLOCKED: Vercel builds from the public archive; server sync pulls anonymously |
| Site itself on the server (leaves Vercel Hobby, which is meant for non-commercial use: terms to verify) | NOT STARTED: needs 8 secrets entered on the server by the owner and a DNS change |
| State from Google Sheets to PostgreSQL | NOT STARTED: new objects first (missions, mandates, outcomes) |
| Heartbeat as a sleeping loop holds one of three runners | OPEN: add a fourth runner or a short timer |
| Self-hosted runners on a public repository | RISK until private; fork approval set to "all external contributors" |

## D. Open items from earlier work (before this release brief)

| Item | Status |
|---|---|
| Choice of wedge: one product category and one region for the first five deals | OWNER |
| Legal entity in Dubai: exact name, and whether it signs contracts | OWNER |
| Dedicated procurement mailbox | OWNER |
| First real deal through the agent; the 9 Nov run that stayed "running" with 0 turns | OPEN: not investigated |
| Zero messages ever proposed or sent: the Act layer is untested on a real case | OPEN: this is F25 |
| TheCompanyAtlas account and connector (customs data, 50 free calls a month) | OWNER |
| Read-only MCP endpoint test (/api/mcp/key) | OPEN |
| WhatsApp / WeChat channels and virtual numbers (Meta Business, WeCom) | OWNER, later |
| EXA search key | OWNER, optional |
| Winner dossier coverage: 215 of 755 with a website, 103 with a contact | OPEN: improve sources |
| Entity resolution across name variants | NOT STARTED |
| APEDA registry resume (page 249 of 484), GAPKI pagination | Runs on its own / OPEN |
| Coverage board: 9 of 42 commodities meet the supplier target; 5 without a price | OPEN |
| Failing Python test: commodity row H0092 missing | OPEN |
| Hetzner prepayment (USD 25): refund by closing the account | OWNER (I draft the request) |

## E. Owner actions outstanding right now

1. Copy the backup key to the Mac (one scp line already given).
2. Replace the Google Drive token that was pasted in the chat (remove rclone access, run the line again).
3. Decide the wedge (category and region) and give the Dubai entity details: both are needed for F25.
4. Later, in one sitting: connect Vercel to GitHub or approve moving the site to the server; add data.sinder.pro in IONOS.

## F. Lessons recorded

1. Check that a product can be ordered before recommending it (Hetzner CX line, OVH order page).
2. A self-written status table is not evidence: the independent review overturned the row "owner approval works".
3. Tests that cannot run are not tests: the approval test had been unbuildable for a day.
4. Numbers from defaults must be labelled as assumptions; the win-chance model was removed.
5. Secrets never pass through the chat; when one did (Drive token), rotate it.
6. A sandbox without direct network needs a durable control channel: the server-ops workflow.
7. Local small models on a 4-core server are slow (10 to 35 s per item) and compete with collection: no cost-saving claim.
8. Usage audit of 9 days: one user, viewing and searching only. More sources do not create deals; five real deals do.
