#!/usr/bin/env bash
# For each workflow in schedule.tab: last start by the server scheduler, last success on GitHub, age, OK/STALE;
# then the key outputs from the last freshness check. Read-only. Names, times and counts only.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot python3 "$GITHUB_WORKSPACE/deploy/ops/scheduler/sched.py" state | python3 "$GITHUB_WORKSPACE/deploy/ops/scheduler/sched.py" report
echo "== last scheduler log lines"; asroot sh -c 'tail -n 8 /var/log/sinder-sched.log 2>/dev/null || echo "(no log yet)"'
echo "== runner services and their CPU/IO weight (runner-priority sets 20/20; default 100)"
asroot sh -c 'for u in $(systemctl list-units --type=service --all --no-legend "actions.runner.*" | awk "{print \$1}" | sed "s/^[^a-z]*//"); do echo "$u $(systemctl show -p CPUWeight -p IOWeight --value "$u" | tr "\n" " ")$(systemctl is-active "$u")"; done; echo "cgroup: $(stat -fc %T /sys/fs/cgroup); load: $(cut -d" " -f1-3 /proc/loadavg); cpus: $(nproc)"'
