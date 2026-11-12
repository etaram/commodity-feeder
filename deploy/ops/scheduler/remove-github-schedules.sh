#!/usr/bin/env bash
# Step to run when switching the timing to the company server (after the dispatch token is on the server):
# removes the GitHub "schedule:" triggers of every workflow listed in deploy/ops/schedule.tab (workflow_dispatch stays),
# so that GitHub and the server never both start the same run. Commit the result, merge it to main, then run the
# server-ops task scheduler-install: it enables the dispatcher only when main has no such trigger left.
#   bash deploy/ops/scheduler/remove-github-schedules.sh && git add .github/workflows && git commit
set -euo pipefail
cd "$(dirname "$0")/../../.."
python3 deploy/ops/scheduler/sched.py remove-schedules .
python3 deploy/ops/scheduler/sched.py check-schedules .
