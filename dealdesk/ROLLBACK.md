# Deal Desk rollback runbook

No passwords or secrets in this file. Secrets live only in Vercel environment variables and GitHub Actions secrets.

## What the system is made of (inventory, 2026-11-04)

| Part | Where | Notes |
|---|---|---|
| Web app (Next.js 15.5, Node 22) | Vercel project `sinder-deal-desk` (prj_4kaUdFkTUOg4Pdbonp8Y2X6yxWy2), domain desk.sinder.pro | Deployed by redeploying with the latest commit; the project is not Git-linked in Vercel |
| Panel UI | `dealdesk/public/panel.html`, served from raw GitHub (main), cached 5 min | A file revert on main switches the UI back within ~5 minutes, no deploy needed |
| Code and public data | GitHub `etaram/commodity-feeder` (public repo) | Tags cannot be pushed through this environment's proxy; baselines are branches |
| Business records | Google Sheets: Leads Engine (users, profiles, activity, pursuits, projects, approvals, contacts, jobs), Supplier Universe (private supplier list), Commodities Tracker | No database yet |
| Private supplier data | `data/private/` (git-ignored, built in Actions) and the Supplier Universe sheet; encrypted copies in `data/web/*.enc` | |
| Workers | 15 GitHub Actions workflows; 3 Claude scheduled tasks (panel worker, bid project manager, tender qualification) | |
| AI | Anthropic API (Claude Haiku 5.5 via ANTHROPIC_API_KEY) | |
| E-mail | Resend (RESEND_API_KEY) | |

## Baseline: baseline-2026-11-04

- Code: branch `baseline-2026-11-04` = commit `5fdb8e8ba681be7717998d748c0414b88279772e` (Node v22.23.4, next 15.5.28, `dealdesk/package-lock.json`).
- Production deployment at baseline: `dpl_8eZMMTDJYcE8DPEcaSd5WxJgf8Vw`.
- Sheet copies (owner's Drive, 2026-11-04 11:20 UTC):
  - Leads Engine -> `1FXxvvJMIMZTM6yOtHmOph9YMxzscmpE6dt-W8Tz3XMw` (70 tabs; Users and Pursuits checked equal to the live sheet)
  - Supplier Universe -> `17U0t-iGFZBfVN4tkoSl8bmQGJjz8ADFJ9-K2HkqlIgA`
  - Commodities Tracker -> `1iPLOM6iXXzbgeqg3wsy_tW7lHB3S0UUVZ--0Or1qMiQ`
- Restore drill (2026-11-04): baseline redeployed to an isolated preview `dpl_GXELBieei3UAukHazd1aGTKuxTcL`, build 88 s, `/login` served 200.
  Signing in on the preview and checking records there needs the owner (a password); pending.

## Rollback, fastest first

1. **Panel UI only (about 5 min):** restore `dealdesk/public/panel.html` from the baseline and push to main.
   `git checkout baseline-2026-11-04 -- dealdesk/public/panel.html && git commit -m "rollback panel" && git push`
2. **Server features without a deploy:** set a flag in Vercel env vars, then redeploy the same deployment (about 90 s):
   - `QUERY_TRANSLATE=off`: no Hebrew-to-English query translation
   - `SUPPLIER_STRICT=off`: supplier research matches any word again
   - `LIVE_TIMEOUT_MS=60000`: wait for live Sheets reads as before
3. **Whole web app (about 2 min):** Vercel, promote or redeploy `dpl_8eZMMTDJYcE8DPEcaSd5WxJgf8Vw` to production
   (Vercel MCP: create_deployment with deploymentId and target production; or the dashboard's "Promote"). Data is untouched.
4. **Data pipeline rules (next scheduled run):** set the Actions variable / revert the file and rerun:
   - incumbents per sector: `INCUMBENT_SCOPE=buyer` restores buyer-wide incumbents (`leads/brain.py`)
   - supplier website check, World Bank sectors: revert `leads/universe.py`, `leads/wb_pipeline.py` to the baseline and rerun `suppliers` / `leads`
5. **Business records (only if data was damaged):** do not overwrite the live sheet with the copy. Compare the damaged tab with
   the baseline copy, and restore only the damaged rows; keep every row written after the baseline (users, decisions, projects).

Never revertible by code: e-mails sent, bids submitted, commitments made. These stay behind explicit approvals.

## Deployments after the upgrade (2026-11-04)
- dpl_Dh43nWPutk9Jy1NLJ4GBeLjGB5TM: current production (deal workspace, project card, search stem).
- dpl_2ZKAwbSqXkFqYXCBQtBgDLwyt1iu: deal workspace without the search stem.
- dpl_ERrELrA3eqJoKZzEofBu31j8brhB: before the deal workspace.
- dpl_8eZMMTDJYcE8DPEcaSd5WxJgf8Vw: baseline before the upgrade.
To go back one step: promote the previous deployment in Vercel (instant). The "Deal Records" tab can stay; nothing reads it
once the route is gone.
