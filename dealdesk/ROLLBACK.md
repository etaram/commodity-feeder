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

## Baseline: baseline-2026-11-12 (current)

- Code: branch `baseline-2026-11-12` = commit `5490bad2` (main at 00:25 Israel time, 12 Nov 2026).
- Production deployment now serving desk.sinder.pro: `dpl_4zZtjnvvhzYFZcutaYACfiHcUAhE` (built from main at `6578f644`, 11 Nov 21:25).
  To go back to it: Vercel MCP create_deployment with this deploymentId and target production, or "Promote" in the dashboard (about 2 minutes). Data is untouched.
- Previous production deployments, newest first: `dpl_DVtsRARVkoQmHV4BjpYQS3nVxcAJ`, `dpl_4q56Wtyk6NcjzUhqrtYM72Mr7RAm`, `dpl_4pWZDHjaaTsd77xZ5cpi6PKHT2u3`, `dpl_t5VSGraVY38Azms8FVv84xEGz4Sm`.
- Server: InterServer VPS; code copy at /opt/sinder/repo, database and Sheets backups under /opt/sinder/backup (encrypted with /opt/sinder/backup.key), copies in Google Drive `Sinder-Backups`.
- Restore drill, 12 Nov 2026 00:20 (workflow restore-drill, run 43110425346): the newest Sheets backup (export of 11 Nov 16:04 UTC) was written into a new empty spreadsheet and read back:
  30 of 30 tabs match, 5,034 of 5,034 rows, all byte-identical, 121 seconds. Tabs created after that export (for example 'Send Guard', 'Missions', 'Outcomes') are not in it; the next nightly backup covers them.
- Staging (preview deployments): separate state spreadsheet, live spreadsheets read-only, mail off. Proof endpoint `/api/staging-check` (preview only).
  Environment variables on the Preview target: STATE_SHEET_ID (staging copy), AGENT_MAIL_LIVE=0, SHEETS_READONLY_IDS, STATE_TABS_EXTRA.
  To undo staging: delete those four Preview variables and set STATE_SHEET_ID (production entry) back to Production and Preview; nothing in production depends on them.
- Mail settings changed on 11 Nov: DNS of sinder.pro now points mail to Zoho (MX mx/mx2/mx3.zoho.com, SPF include:zohomail.com, DKIM selector `sinder`). Before: IONOS (MX mx00/mx01.ionos.com, SPF include:_spf-us.ionos.com). Changing back is done in the IONOS DNS screen by the owner.
- Mail look: `MAIL_HTML=0` returns to plain-text mail; removing `ZOHO_FROM_ADDRESS` returns the visible sender to the mailbox address; removing `MAIL_ABOUT` removes the first-contact note.

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

## Owner-only approval (SEND_APPROVERS), live since 12 Nov 2026 09:04

Production deployment dpl_8oMuMqJFixYTsFSGsDveJtUXCA31. With the variable set, only the listed personal account approves
an outgoing message (panel, Telegram, campaign authorisation, outbox reconcile).

Going back safely. Removing SEND_APPROVERS, or redeploying an older deployment, brings back the earlier rule in which the
shared team login can send. That is NOT a safe way back. If this change has to be undone:

1. First set AGENT_MAIL_LIVE=0 for Production and redeploy: nothing can leave (lib/mailer.ts returns before any connection).
2. Only then remove the variable or redeploy the older deployment (dpl_4zZtjnvvhzYFZcutaYACfiHcUAhE).
3. Sending is opened again (AGENT_MAIL_LIVE removed) only together with a working approver rule.

Current state: the owner's live account has a password he does not remember and there is no password reset, so nobody
can approve a send on the live site or by Telegram until his account is restored by him. This is a temporary stop of
sending, not a finished commercial path.

## Server instance next to the live site (12 Nov 2026)

The live system on Vercel is kept untouched as the fallback: production deployment dpl_8oMuMqJFixYTsFSGsDveJtUXCA31,
previous dpl_4zZtjnvvhzYFZcutaYACfiHcUAhE. Nothing in Vercel (settings, deployments, domain, Telegram webhook) is changed.

Code backup: tag `vercel-live-2026-11-12` = commit bb2e6c23d4adf8b52ce0e07d4a7e74c2c9610a1a (origin/main when the server
work started). To go back in code: `git checkout vercel-live-2026-11-12`.

The server system (branch `release/server`, checkout /opt/sinder/server-instance, compose project `sinder-server`,
address https://desk.216-158-234-218.sslip.io) is a separate instance until the owner moves the domain. While both run it
cannot send anything: AGENT_MAIL_LIVE=0, no Resend key, no web push key, Telegram off (TELEGRAM_OFF=1), and no cron
service. It shares the same Google Sheets state, so actions taken in it are real data changes.
To remove it: `docker compose -p sinder-server -f /opt/sinder/server-instance/deploy/docker-compose.server.yml down`
and delete its block from /opt/sinder/gateway/Caddyfile (a copy before the change is kept next to it).
