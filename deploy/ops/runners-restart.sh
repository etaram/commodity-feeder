#!/usr/bin/env bash
# Restarts any self-hosted runner service that is not active (e.g. r3 shown "offline" in the admin panel) and lists
# all runner services afterwards. Busy runners are left alone. Prints service names and states only.
set -euo pipefail
asroot() { docker run --rm --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- "$@"; }
asroot sh -c 'for u in $(systemctl list-units --all --type=service --no-legend "actions.runner.*" | awk "{print \$1}"); do
  s=$(systemctl is-active "$u" || true); if [ "$s" != active ]; then echo "restarting $u (was $s)"; systemctl restart "$u" || systemctl start "$u" || true; fi; done
  sleep 5; systemctl list-units --all --type=service --no-legend "actions.runner.*" | awk "{print \$1, \$3, \$4}"'
