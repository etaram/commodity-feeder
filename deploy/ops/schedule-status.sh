#!/usr/bin/env bash
# For each workflow in schedule.tab: last start by the server scheduler, last success on GitHub, age, OK/STALE;
# then the key outputs from the last freshness check. Read-only. Names, times and counts only.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot python3 "$GITHUB_WORKSPACE/deploy/ops/scheduler/sched.py" state | python3 "$GITHUB_WORKSPACE/deploy/ops/scheduler/sched.py" report
echo "== last scheduler log lines"; asroot sh -c 'tail -n 8 /var/log/sinder-sched.log 2>/dev/null || echo "(no log yet)"'
