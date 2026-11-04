# Deal Desk v2: implementation log

Brief: "Implementation brief for Claude: upgrade the existing Sinder Deal Desk" (2026-11-04). Work runs in reversible slices;
each entry says what changed, how it was tested, how to roll it back, and what is still open. Targets in the brief are
targets, not results.

## Slice 1: inventory and baseline (2026-11-04) - done, one check pending

- Inventory: see ROLLBACK.md (Vercel app, panel from raw GitHub, Google Sheets as the record store, GitHub Actions workers,
  3 Claude scheduled tasks, Anthropic, Resend). No database, no object storage, no uploaded documents found.
- Baseline: branch `baseline-2026-11-04` (commit 5fdb8e8), production deployment dpl_8eZMMTDJYcE8DPEcaSd5WxJgf8Vw,
  copies of the three Google Sheets (IDs in ROLLBACK.md). Git tags are blocked by this environment's proxy (HTTP 403), so the
  baseline is a branch.
- Restore drill: an isolated preview rebuilt from the baseline deployment, build time 88 s, /login answered 200. A first
  attempt from the Git branch failed (`git_info_fail`: the Vercel project is not linked to Git), so restores use redeploys.
- Pending (needs the owner): sign in on the restored preview and open a supplier, a pursuit and the Users tab.

## Slice 2: audit issues reproduced (2026-11-04)

| # | Issue | Reproduced? | Evidence |
|---|---|---|---|
| A1 | Calculator "Margin" acted as markup | yes | code: `bid = landed * (1 + m)`; 40M+1M, 7%, 50% gave 65,805,000 |
| A2 | Incumbents from buyer-wide history | yes | `leads/brain.py` used all of a buyer's winners, any sector |
| A3 | Quick analysis vs decision conflict | yes | prompt asked for Go/No-go/Need info as free text, never compared |
| A4 | Hebrew search returns little or nothing | yes | activity log: profile "מוצרי חשמל" 11 suppliers, "שואבי אבק רובוטיים" almost none |
| A5 | Missing deadline shown as 0 days | partly | no-deadline rows have blank days and pass the min-days filter with no label; 0-day rows found all have a real deadline today |
| A6 | "diesel generator" returns fuel traders, ozone generators | yes | any-word match (`hits > 0`) |
| A7 | Wrong company websites (deutschebahn.com, pec.it) | yes | notice and e-mail domains accepted without a name check |
| A8 | Contact badge can mean website only | yes | filter "With contact details" = has website |
| A9 | Today "1,499 in your profile" vs For me 0 | yes | Today counts the company profile, For me the personal one |
| A10 | World Bank projects in wrong sectors | yes | 466 of 923 "Other"; housing and farm finance as Defence |
| A11 | Raw Markdown in AI output | yes | AI text shown with textContent |
| A12 | /api/panel/get timeouts | yes | 33 timeouts in 5 days (Vercel runtime errors) |
| A13 | Maize 3 vs 17 suppliers; grant categories; contact sector fragments | not yet | open |

## Slice 3: correctness fixes (2026-11-04)

| # | Fix | Test | Rollback |
|---|---|---|---|
| A1 | Gross margin: price = cost / (1 - m), 0 <= m < 95%; shows gross profit, margin and markup | tests/econ.test.mjs, 10 checks pass (43,870,000 at 50% -> 87,740,000) | panel.html revert |
| A2 | Incumbent = same-sector winners of that buyer | code path; result after the next leads run | `INCUMBENT_SCOPE=buyer` |
| A3 | Structured VERDICT line; a conflict with the engine decision is shown, decision unchanged | manual | panel.html revert |
| A4 | Hebrew to English: built-in dictionary first, AI (Haiku, cached) only for unknown words; profile keywords keep the original and the English | tests/search.test.ts, 11 checks pass | `QUERY_TRANSLATE=off` |
| A5 | "no deadline stated" label instead of nothing | manual | panel.html revert |
| A6 | Supplier research: short product phrases must match every word (75% for 4+) | tests/search.test.ts | `SUPPLIER_STRICT=off` |
| A7 | Website shown only when the domain matches the company name; certified-mail and generic domains rejected | 11 sample cases (Rolls-Royce/deutschebahn and pec.it rejected, ADM, Kuehne + Nagel, Jindal SAW kept) | revert leads/universe.py |
| A8 | Filter renamed "With a website" (e-mail and phone load when the company opens) | manual | panel.html revert |
| A9 | Today label says company profile, and that For me is personal | manual | panel.html revert |
| A10 | World Bank sector from the Bank's own sector1 field, title only as fallback | 15 sample sector names | revert leads/wb_pipeline.py |
| A11 | AI answers rendered: headings, bold, bullets, links, tables; escaped first | manual | panel.html revert |
| A12 | Live Sheets read limited to 9 s, then the encrypted snapshot | type-check, build | `LIVE_TIMEOUT_MS=60000` |

## Slice 4: source registry (2026-11-04)

- `leads/registry.py` -> `data/registry/sources.json|csv`, rebuilt after every leads run from health.json and output files.
- First run: 73 active, 2 degraded (Google Trends: unofficial library, official API access not granted), 4 implemented but not
  scheduled (Zambia captcha, Tanzania late data, Georgia, Ecuador), 29 backlog sources "discovered" (link researched only).
  13 of the 42 backlog sources are already covered by working connectors (TED, PNCP, ChileCompra, Kenya, South Africa, Etimad,
  World Bank, AIIB, AfDB, IDB, India, UN Comtrade via markets, Trends).

## Not done yet (next slices)

Evidence/provenance entities, project stages, commodity signal engine, unified private deal workflow, compliance matrix and bid
package, v1/v2 switch in the UI, the 240 supplier capability matches, the 30 labeled search cases with human review, and moving
large regenerated data files out of Git history.

## Slice 5: visual design v2 (2026-11-04), superseded by slice 6

(First pass "chart room" in teal; replaced the same day by the brief section 9 palette.)

## Slice 5 (original notes)

- Harbor-navy band for brand and tabs, cool chart-paper background, signal teal for actions, buoy red for urgency.
- Frank Ruhl Libre (Hebrew and Latin serif) for headings and figures; IBM Plex Sans / Sans Hebrew for data; no monospace labels.
- Score rings: every score is drawn as a ring filled to its value (0-100).
- Mixed Hebrew/English lines isolated per fragment (bdi), so the order stays right in RTL.
- Light and dark, mobile checked with screenshots (stub data). The theme is one CSS layer: `?ui=classic` switches back
  (remembered per browser), `?ui=v2` returns. Rollback: remove the v2 block from panel.html.

## Slice 6: design per brief section 9 (2026-11-04)

- Palette changed to the brief's navy and restrained gold on light surfaces, contrast computed for every text pair (DESIGN.md).
- Five destinations (side navigation on wide screens, bottom bar on phones); all 14 views kept as sub-tabs; deep links kept.
- "Projects" renamed "Bid projects" so private bids are not confused with global projects.
- Fonts: dropped the extra serif; IBM Plex (both scripts) plus Secular One for the mark only.
- Tests: screenshots at 390/768/1280/1440 px in English and Hebrew, no horizontal overflow, no script errors; classic switch
  shows the old 14 tabs. Rollback: `?ui=classic`, or remove the v2 block and nav.dest from panel.html.

## Slice 7: design skills, accessibility, Today action queue (2026-11-04)

Skills (brief 9.1). Available locally: frontend-design. Fetched and read from their official repositories (raw files,
2026-11-04; the GitHub API for those repos is blocked here, so file hashes stand in for commit ids):
- web-design-guidelines (vercel-labs/agent-skills, sha256 f4647ca866a3) + its rules file web-interface-guidelines/command.md
- webapp-testing (anthropics/skills, d91970639e9f): Playwright reconnaissance-then-action, used for all checks below
- react-best-practices (vercel-labs/agent-skills, MIT, 51b7349e77ec): applied async-parallel to the live Sheets reads
- together-ai-design-skill: no public source given; not used.

Accessibility (axe-core 4.10.2, WCAG 2.0/2.1/2.2 AA + best practice, 5 screens, stub data):
- before: 11 selects without names (critical), no h1, detail panes as top-level complementary landmarks
- after: 0 violations; keyboard walk: skip link first, every control focusable with a visible outline
- also: live status region, 44 "..." -> "…", theme-color, touch-action, balanced headings.
  Screen-reader and zoom checks on the live site: pending (need a signed-in session).

Today (brief 9.5): "What needs your attention" queue first: approvals waiting, bid projects with a next step or missing
item, Pursue tenders closing in 3-21 days without a project (open items: value, competition, eligibility), research
finished in the last 2 days. Each item: what, why, deadline (or "no deadline stated"), what is open, one next action that
opens the exact record. Streams: projects and buyers in the leading column, commodities in the other.

## Slice 8: pipeline fixes verified on live data (2026-11-04)

- Incumbents (A2): TED-762196-2026 now shows Vogelsang Austria and Börger (same sector) instead of the buyer's IT suppliers; score 96, Pursue.
- World Bank sectors (A10): the API moved sectors to `major_sectors`; read from there. "Other" fell from 468 to 137 of 928 projects.
- Supplier websites (A7): sites kept only when the domain matches the company: 142,628 -> 109,391 suppliers with a website.
- Supplier universe: 607,183 suppliers; tier 1-2 = 84,925 (13,723 + 71,202).
- Bug found and fixed: the suppliers workflow copied all of data/web over newer files (a stale tender index and panel
  snapshot); it now owns only data/web/suppliers.enc.

## Slice 9: tender detail as a guided sequence (2026-11-04)

- v2 tender detail: identity, then the engine decision with what is still open (value, eligibility, competition, deadline),
  then five ordered steps: understand, requirements, suppliers and partners, price and logistics, decide and act.
  Each step shows done / in progress / not yet from the job records; one primary action: the first step not done
  (eligibility, then quote, then track or start the bid project; an existing project is opened, never duplicated).
- The step results, the price estimate and then the notice details follow; WhatsApp sharing stays secondary.
- Same buttons, ids and handlers as before; classic keeps the old row. Tests: screenshots 1440 px Hebrew, 390 px English,
  classic; axe-core clean. Rollback: `?ui=classic`, or remove tenderSteps() from panel.html.

## Slice 10: private deal workspace (2026-11-04)

- Store: hidden tab "Deal Records" in the engine sheet, append-only (every save is a new version, latest wins, delete is a
  "deleted" version), written with RAW input so quote text cannot run as a formula. API `/api/deal`, analysts and admins only,
  checked on the server; nothing is sent outside the system.
- Panel (v2, tender step 5 "Deal workspace"): header with stage, owner, deadline, next action, blocker; requirements matrix
  (document, page, mandatory, status, evidence; "met" needs evidence; not ready while a mandatory item is open; the bid
  project agent's conditions shown read-only); quote comparison (source required, basis = Incoterm + currency + unit, mixed
  bases flagged and no "lowest" pick, expired validity, unconfirmed availability); economics (principal or agent, dated cash
  flows, freight and insurance not double-counted, financing on the negative balance, peak capital and days tied up, base
  and downside).
- Tests: tests/econ.test.mjs 19 checks (9 new for cash flows); type-check; screenshots 1440 px Hebrew and 390 px English,
  no overflow, no script errors. Rollback: remove the "a-ws" button (the tab is inert without it) or `?ui=classic`.

## Slice 11: global projects by stage (2026-11-04)

- Planned projects (World Bank pipeline and others) show a project card: stage, funding (proposed / approved / unknown), the
  Bank's financing labelled as financing and not project cost, addressable value "unknown until the procurement plan lists
  the packages", how the buyer will buy, and open tenders in the same country with the same buyer or sector.
- Rollback: remove projectStageHtml() from panel.html.

## Slice 12: evaluation set, seeds, commodity source (2026-11-04)

- tools/search_eval.py: 30 labeled cases (16 tenders, 14 suppliers, Hebrew and English pairs) on the real indexes, the
  panel's own dictionary and matching rules. Labels are a first pass by the builder, pending human review. Precision here
  measures translation and exact matching, not recall. Output: data/probe/search_eval.md.
- Found and fixed: dictionary entries with two words ("maize corn", "chicken poultry", "milk dairy", "asphalt bitumen")
  required both words under strict matching, so Hebrew "תירס" found fewer suppliers than "maize" (part of A13).
- tools/seed_check.py: 27 of the 28 brief seeds are already in the supplier index (Apical is not); several name matches are
  noisy (Olam, ETG, ADM, Wilmar) and must be merged by hand, not added. POWERCHINA (via Sinohydro) and CSCEC are EPC
  partners, not suppliers. Output: data/probe/seed_check.md.
- World Bank Pink Sheet (S04) was already the source of price_trends; the registry now says so, with the licence.
- Operator guide: dealdesk/OPERATOR_GUIDE.md (Hebrew).
- Eval result after the fixes (2026-11-04 16:08Z run in Actions): 30 cases, 28 with results, precision@10 0.99 by the
  first-pass labels; every Hebrew query now returns the same set as its English pair (maize: 2 -> 25). Plural and singular
  match each other (transformers 22 -> 34, solar panels 2 -> 4). Open: supplier recall for specific products is low
  (diesel generator 1, robot vacuum cleaners 0 of 84,925 tier 1-2 suppliers) because the product field holds short HS or
  notice wording; this needs richer product data, not a looser match.

## Slice 13: the brain (2026-11-04 evening)

Owner's ask: the first tender shown must not be an off-road car for a regional council; country-level intelligence;
how information becomes a deal; a competitive edge at low cost. See dealdesk/BRAIN.md.
- Ranking: `leads/dealfit.py` replaces the objective score. Continuous 0-100 built for a cross-border sourcing firm
  (EV, size band, goods share, foreign access or IFI financing, proven suppliers per sector, timing, emerging market,
  partner country, repeat buyer) with named penalties (licensed goods, on-site services, routine local purchases, small
  municipal buys, closed access, set-asides, exemptions, late, oversized) and the Profile weights as a square-root
  multiplier. Dry run on 68,114 live notices: 415 notices tied at 96 before; now one at the top (green hydrogen,
  $40M, Scottish council), Amgros pharma frameworks fall from 96 to 43 with the reason shown, the regional-council
  vehicle to 24. Sheet formula AC now = score x supplier-match factor (the weights are no longer applied twice).
- Explanations: `fit_why`, `fit_flags`, `route` merged into every tender grid on the server from the public index;
  the panel shows "Why this rank" with Relevant / Not relevant buttons (logged as fit_feedback);
  `tools/fit_calibrate.py` reports rule-by-rule agreement with the owner's marks.
- Plays (`leads/plays.py` -> data/leads/plays.csv, sheet tab Plays): supply the winner (69), arbitrage gap (205),
  pre-tender approach (63); emerging markets first; shown on Today and on the country page.
- Country intelligence: `/api/panel/country?c=ISO3` + the Country sub-tab (open tenders by sector and value, foreign
  access share, planned projects, top buyers and cycles, who wins, imports and premiums, plays, news, risk, integrity).
- News: `leads/gdelt.py`: Google News RSS per watched country (GDELT throttles GitHub's shared IPs: HTTP 429, kept as
  a polite fallback). Test run: 73 headlines for 3 countries.
- Who I know: hidden tab My Network (LinkedIn export), `/api/panel/know`, shown on tenders and plays to analysts and admins.
- Supplier aggregates (counts only) published for the brain: data/leads/supplier_sectors.csv, supplier_hs.csv.
- Rollback: `score` falls back to the old objective score if dealfit raises; remove the dealfit call in leads/run.py
  to restore it fully; the sheet formula AC can be restored from the log of 2026-11-04 (weights x score, capped 100).
- Pending: first live leads run with the new score; owner's marks for calibration; IFI procurement plans, LEI groups,
  exchange filings, freight and FX indexes (BRAIN.md "next").

## Slice 14: context and reach (2026-11-04, late evening)

- World briefing feed `leads/briefing.py`: Google News RSS topic queries (trade policy, shipping, commodities, geopolitics,
  regional infrastructure x6, Israel trade, China outbound) plus the owner's own feeds (sheet tab Briefing Sources:
  podcasts, newsletters, YouTube channels, expert blogs; kind "company" watches a company by name). Items tagged with
  countries, commodity group and signal type; "news leads" (company + build/award verb) become plays. Test: 645 items,
  16 news leads in 48 h.
- Daily world brief `/api/panel/brief` (lib/brief.ts): one Haiku call a day, cached in the hidden tab Briefs, Hebrew or
  English, every line cites a numbered source, no outside knowledge; a button on Today builds it when missing.
- World Bank `leads/wb_plans.py`: procurement plans from the Documents API (1,118 projects with a plan in 90 days, PDF
  links) -> "procurement plan published" plays and a country-page section; "Read the plan (AI)" lists the packages on
  click (web_fetch, on demand). IPF contract awards from Finances One view DS01154 (147,872 rows, FY filter works;
  the first run used the wrong view id and got 0 rows, fixed for the next run) -> country-page WB winners.
- GLEIF LEI `leads/lei.py`: ultimate parents for repeat winners and play entities, 250 lookups a run, cached in Git;
  shown as "group" on the country page winners. Untested against the live API until the next leads run.
- ECB FX `leads/fx.py`: USD per unit for 20 currencies with 30-day change -> data/leads/fx.csv (for the margin model
  and quotes in other currencies; wiring into the deal workspace is next).
- Sunday digest now carries a country watch for the profile's countries (open, Pursue, planned, 3 plays, 5 headlines).
- Search evaluation on the enriched supplier index: diesel generator 1 -> 11 suppliers, transformers 34 -> 228, solar
  panels 4 -> 43, ductile iron pipes 2 -> 4, medical equipment 51 -> 2,337 (contract history now counts; ranked below
  own products). Robot vacuum cleaners still 0: no such supplier in the universe.
- Oracle Cloud runner for geoblocked portals: dealdesk/RUNNER_ORACLE.md (needs the owner's account; nothing built).

## Slice 15: channels, documents, app, brand, v3 (2026-11-04, night)

- Telegram bot (lib/telegram.ts, /api/telegram): commands and free text over the system's own tools; chat linked by a
  per-user code; alerts (morning theses, brief); token accepted under the bot's own variable name; webhook set by one
  click (or automatically when an admin opens Today). Pending: the owner's first /start.
- Document reading: /api/deal/docs reads a notice page, PDF or bidding document into the requirements matrix.
- Deal reverse engineering: /api/panel/reverse: image or PDF -> facts (read vs inferred, redactions), own data, candidate
  counterparties with evidence, price check, way in. File processed in memory only.
- Freshness: closed notices dropped server-side from every grid; isClosed() handles "04 Dec 2026" (a slice bug that
  would have parsed year 202 was caught in tests).
- PWA: manifest, service worker (shell only, data never cached), Web Push with VAPID implemented in Node crypto (no
  dependency); install and notification box on Today; push for the brief and the morning theses. Keys in Vercel.
- Brand: mark (two trade routes forming an S), light and dark logos, favicon, 512 icon.
- v3 (default): dark theme, Today as a morning page (greeting, rings, step bars, sparklines), command palette Ctrl/Cmd+K.
  `?ui=v2` light, `?ui=classic` old. axe-core: 0 violations on 5 views after a contrast fix on pressed controls.
- Regional relay (sinder-relay-eu, Vercel fra1): collectors fall back on 403/451; verified Frankfurt egress.
- Attention: Google Trends daily trending RSS per country and Wikipedia pageviews; Bright Data provider optional.
- Reddit and public Telegram channels as briefing sources.
