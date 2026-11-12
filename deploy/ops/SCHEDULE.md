# Timed workflows and the server scheduler

GitHub skips or delays scheduled workflows on this repository (on 11-12 Nov 2026 the hourly panel ran 3 times in
17 hours, a suppliers run created by schedule never got a job, and the nightly backup schedule produced no run). The
company server therefore starts the timed workflows itself through the GitHub `workflow_dispatch` API, and checks
every 30 minutes that the key outputs are fresh.

## Inventory (all workflows with a `schedule:` trigger)

Times are UTC. Duration: median / slowest of the last 30 successful runs (minutes), measured 12 Nov 2026.

| Workflow | Cron (UTC) | What it does | Duration median / max | Concurrency group |
|---|---|---|---|---|
| panel.yml | `35 * * * *` | live data of the web panel (encrypted panel files) | 1 / 1 | panel-live (cancels the running one) |
| company-check.yml | `20 * * * *` on GitHub; back-to-back on the server | company website and register checks, record refinement | 46 / 60 | company-check |
| describe.yml | `50 * * * *` (also after each company-check) | English description of checked companies, local models | 43 / 76 | describe |
| leads.yml | `10 */2 * * *` light set; `40 4,16 * * *` heavy set | tenders and leads from ~60 portals, merge, push to Sheets | 67 / 136 | repo-data-writes (shared with press) |
| coffee-sellers.yml | `35 */2 * * *` | coffee exporters from public seller profiles | 13 / 65 | coffee-sellers |
| suppliers.yml | `40 1 * * *`, `40 13 * * *` | award records, supplier universe build, winners | 48 / 182 | suppliers-writes |
| feed.yml | `40 5 * * *`, `10 21 * * *` | commodity price feed for the tracker | 4 / 10 | commodity-feed |
| press.yml | `50 5,15 * * *` | press and news signals | 53 / 111 | repo-data-writes (shared with leads) |
| backup.yml | `40 1 * * *` | encrypted database backup with restore test, Sheets export backup | 2 / 2 | backup |
| agent-brief.yml | `40 2 * * *` | morning "Agent Brief" tab | 0 / 1 | agent-brief |
| israel.yml | `50 3 * * *` | tenders pages of ~1,000 Israeli public bodies | 1 / 22 | israel |
| sanctions.yml | `20 4 * * *` | sanctions lists refresh | 0 / 1 | sanctions |
| trends.yml | `17 3 * * 1` (Monday) | Google Trends for top market signals | 6 / 6 | trends |
| heartbeat.yml | `17 */6 * * *` | safety net: restarts overdue workflows (stays on GitHub) | 352 / 354 | heartbeat |
| watchdog.yml | `7 * * * *`, `37 * * * *` | safety net: restarts overdue workflows (stays on GitHub) | 0 / 0 | watchdog |

15 scheduled workflows; 13 move to the server scheduler (`deploy/ops/schedule.tab`). heartbeat and watchdog stay on
GitHub: they only start a workflow that is overdue, so with a working server scheduler they find nothing to do.
Slowest: suppliers (up to 3 hours, the universe rebuild runs last), leads (up to 2h16m), press (up to 1h51m).
Most important for the live panel and the Sheets: panel, leads, suppliers, feed and backup.

## How the server starts them

- `deploy/ops/schedule.tab`: one line per trigger, cron in UTC, the workflow, the max age for STALE, and inputs.
  leads gets `only=light` / `only=heavy` (the same step sets GitHub's two crons chose); coffee-sellers gets
  `scheduled=yes` (so a timed run does not force the weekly registry refresh that a manual run forces).
- company-check is `@continuous`: the build of the supplier universe needs it all day (12 Nov: 1,043,458 records,
  309,818 websites in the check queue, 18,167 checked; GitHub ran the "hourly" job 8 times in 24 hours, busy 24% of
  the time). The dispatcher starts it again on the first 5-minute tick after the previous run has finished, never
  while a run is queued or running; its concurrency group `company-check` is the second guard against overlap.
  describe follows each company-check run (workflow_run), so it speeds up with it.
- `sinder-sched-dispatch.timer` runs `sched.py dispatch` every 5 minutes (at :00:20, :05:20, ...). It starts every
  line whose cron time fell since the previous tick (at most 30 minutes back after an outage, one start per line).
  It does not start a workflow that already has a run waiting to start; a running one is left to its concurrency group.
- Every start and skip is logged in `/var/log/sinder-sched.log`; the state is in `/var/lib/sinder-sched/dispatch.json`.
- Credentials: a fine-grained GitHub token limited to this repository with "Actions: read and write" only, stored on
  the server in `/opt/sinder/secrets/gh_dispatch.token` (root only, mode 600). The owner adds it as the repository
  secret `SCHED_DISPATCH_TOKEN`; the server-ops task `scheduler-install` writes it to that file. The token of the
  self-hosted runners is a registration token and cannot start workflows.

## No double runs

The dispatcher is enabled by `scheduler-install` only when both are true: the token works, and the workflows on `main`
no longer have GitHub `schedule:` triggers. Until then the GitHub schedules stay as they are and the dispatcher is
installed but disabled. To switch over:

1. Owner: add the repository secret `SCHED_DISPATCH_TOKEN` (see above).
2. `bash deploy/ops/scheduler/remove-github-schedules.sh`, commit `.github/workflows`, merge to main.
3. Run the server-ops task `scheduler-install` (from main). It writes the token and enables the dispatcher.

To go back: put the `schedule:` blocks back (git revert of step 2) and run `scheduler-install` again; it disables the
dispatcher because main has schedules again.

## Freshness check and alert

`sinder-sched-fresh.timer` runs `sched.py fresh` at :07 and :37 every hour, over `deploy/ops/freshness.tab`:

| Output | Source of the time | Max age |
|---|---|---|
| panel-live | last commit on main of `data/web/panel_live.sha` | 3 h |
| tenders-leads | last commit on main of `data/web/tenders.json.gz` | 5 h |
| supplier-universe | last commit on main of `data/leads/supplier_sectors.csv` (written by the universe build) | 16 h |
| commodity-feed | last commit on main of `data/run_log.json` | 18 h |
| sheets-export | `/opt/sinder/backup/sheets/last-manifest.json` on the server | 26 h |
| db-backup | newest `/opt/sinder/backup/db/*.enc` on the server | 26 h |

Thresholds are the normal interval plus the slowest normal run plus a margin. Workflow ages in `schedule-status`
use the max-age column of `schedule.tab`.

Results go to `/var/lib/sinder-sched/freshness.json` and, without any error text, to `_status/freshness.json` in the
copy of the repository that the data gateway serves (behind its secret path). When an item turns STALE, a Telegram
message goes out through the existing bot, repeated every 12 hours while it stays stale, and a short note when all are
fresh again. It is sent only if the server's `deploy/.env` already holds the bot token (`TELEGRAM_BOT_TOKEN`, or the
variable named after the bot) and an owner chat id for alerts (`SCHED_ALERT_CHAT_ID`, `TELEGRAM_ALERT_CHAT_ID`,
`ALERT_CHAT_ID`, `OWNER_CHAT_ID`, `TELEGRAM_OWNER_CHAT_ID` or `TELEGRAM_CHAT_ID`); otherwise it is only logged.

## Background jobs run at low priority

Heavy background work (company checks, embeddings in describe, refinement, the universe build) must run at low
priority, so it uses all spare CPU without slowing the database, the data gateway or the website. Rule for anything
new: start it under `nice -n 19 ionice -c3`, or inside a systemd unit/slice with a low `CPUWeight` and `IOWeight`.

The self-hosted runners are systemd services (`actions.runner.*.service`, created by `svc.sh` in deploy/runners.sh),
so all their jobs can be weighted at once: the server-ops task `runner-priority` sets `CPUWeight=20` and
`IOWeight=20` on them with `systemctl set-property` (applies at once, no restart, kept across reboots). Every other
service keeps the default weight 100, so under contention the database, gateway and web app get about 5 times the
CPU share of the runners, and the runners take everything that is left. Containers started by a job with
`docker run` sit outside the runner service and are not covered.

## Server-ops tasks

- `scheduler-install`: installs or updates the scheduler, writes the token from the secret, decides on the dispatcher.
- `schedule-status`: per workflow the last start by the server, last success on GitHub, age, OK/STALE; company-check
  runs and busy minutes in the last 24 hours; refine progress (`data/leads/refine_progress.json`: processed,
  websites_checked, website_check_queue); per key output its age and OK/STALE; timer and alert readiness.
  Names, times and counts only.
- `runner-priority`: low CPU and disk weight for the runner services (see above).
