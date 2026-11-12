#!/usr/bin/env bash
# Gives the self-hosted GitHub runners a low CPU and disk weight, so the heavy background jobs (company checks,
# embeddings, refinement) use all spare capacity but yield at once to the database, the data gateway and the website.
# Uses "systemctl set-property": it applies to the running services at once, with no restart (a running job is not
# interrupted), and is kept across reboots (systemd writes it under /etc/systemd/system.control).
# Weights are relative: the default for every other service is 100. Undo: run with CPU=100 IO=100.
# Containers that a job starts with "docker run" are not under the runner service and keep the default weight.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
CPU="${RUNNER_CPU_WEIGHT:-20}"; IO="${RUNNER_IO_WEIGHT:-20}"
asroot sh -c "
  echo \"cgroup: \$(stat -fc %T /sys/fs/cgroup) (cgroup2fs = weights apply)\"
  units=\$(systemctl list-units --type=service --all --no-legend 'actions.runner.*' | awk '{print \$1}' | sed 's/^[^a-z]*//')
  [ -n \"\$units\" ] || { echo 'no runner services found (actions.runner.*)'; exit 1; }
  for u in \$units; do
    before=\$(systemctl show -p CPUWeight -p IOWeight --value \"\$u\" | tr '\n' ' ')
    systemctl set-property \"\$u\" CPUWeight=$CPU IOWeight=$IO
    echo \"\$u: CPUWeight/IOWeight before: \$before-> now: \$(systemctl show -p CPUWeight -p IOWeight --value \"\$u\" | tr '\n' ' ')\"
  done
  echo \"runner services: \$(echo \"\$units\" | wc -l); load: \$(cut -d' ' -f1-3 /proc/loadavg); cpus: \$(nproc)\"
"
