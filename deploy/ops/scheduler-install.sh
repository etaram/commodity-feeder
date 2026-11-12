#!/usr/bin/env bash
# Installs the server-side scheduler (deploy/ops/scheduler) as systemd timers on the company server:
#   sinder-sched-fresh.timer     every 30 minutes, checks the age of the key outputs (enabled now)
#   sinder-sched-dispatch.timer  every 5 minutes, starts the workflows in schedule.tab through the GitHub API
#                                (enabled only when the dispatch token is on the server AND main no longer has the
#                                GitHub "schedule:" triggers of those workflows, so nothing runs twice)
# If the repository secret SCHED_DISPATCH_TOKEN exists, it is written to /opt/sinder/secrets/gh_dispatch.token
# (root only, mode 600) through standard input; it never appears in a command line or in the log.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
W="$GITHUB_WORKSPACE"
if [ -n "${SCHED_DISPATCH_TOKEN:-}" ]; then
  printf '%s' "$SCHED_DISPATCH_TOKEN" | docker run -i --rm --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- \
    sh -c 'umask 077; mkdir -p /opt/sinder/secrets && chmod 700 /opt/sinder/secrets && cat > /opt/sinder/secrets/gh_dispatch.token.new && chmod 600 /opt/sinder/secrets/gh_dispatch.token.new && mv /opt/sinder/secrets/gh_dispatch.token.new /opt/sinder/secrets/gh_dispatch.token'
  echo "dispatch token: written from the repository secret SCHED_DISPATCH_TOKEN"
else
  echo "dispatch token: the repository secret SCHED_DISPATCH_TOKEN does not exist (or is empty); nothing written"
fi
asroot bash "$W/deploy/ops/scheduler/_install_root.sh" "$W"
