#!/usr/bin/env bash
# Removes the GitHub "schedule:" triggers of every workflow listed in deploy/ops/schedule.tab (workflow_dispatch
# stays), so that GitHub and the dispatcher (heartbeat.yml) never both start the same run. Safe to re-run.
#   bash deploy/ops/scheduler/remove-github-schedules.sh && git add .github/workflows && git commit
set -euo pipefail
cd "$(dirname "$0")/../../.."
python3 deploy/ops/scheduler/sched.py remove-schedules .
python3 deploy/ops/scheduler/sched.py check-schedules .
