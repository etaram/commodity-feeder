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
