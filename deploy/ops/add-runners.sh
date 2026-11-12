#!/usr/bin/env bash
# Adds self-hosted runners r4..r6 (same user, label "sinder") so server tasks do not wait behind long data jobs.
# The registration token comes from the repository secret RUNNER_REG_TOKEN (GitHub > Settings > Actions > Runners >
# New self-hosted runner shows it; valid one hour). It is passed to this task only, written to a root-only file for the
# duration of the install and removed at the end. Never printed. Existing runners are not touched.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
# asroot without -i drops standard input; this task feeds the token and the install script through it
asroot_i() { docker run --rm -i --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- "$@"; }
[ -n "${RUNNER_REG_TOKEN:-}" ] || { echo "RUNNER_REG_TOKEN is not set: add the repository secret first"; exit 1; }
FROM="${RUNNERS_FROM:-4}"; TO="${RUNNERS_TO:-6}"
tmp=$(mktemp); chmod 600 "$tmp"; printf '%s' "$RUNNER_REG_TOKEN" > "$tmp"
asroot_i sh -c "mkdir -p /opt/sinder/secrets && chmod 700 /opt/sinder/secrets && cat > /opt/sinder/secrets/runner_reg.token && chmod 600 /opt/sinder/secrets/runner_reg.token" < "$tmp"
rm -f "$tmp"
asroot sh -c "test -s /opt/sinder/secrets/runner_reg.token" && echo "token staged on the server" || { echo "token was not staged"; exit 1; }
asroot_i bash -s "$FROM" "$TO" <<'ROOT'
set -euo pipefail
FROM=$1; TO=$2; TOKEN=$(cat /opt/sinder/secrets/runner_reg.token)
VER=$(curl -fsS https://api.github.com/repos/actions/runner/releases/latest | sed -n 's/.*"tag_name": *"v\([^"]*\)".*/\1/p' | head -1)
ARCH=$(uname -m | sed 's/x86_64/x64/; s/aarch64/arm64/')
for i in $(seq "$FROM" "$TO"); do
  d=/home/runner/r$i
  if [ -f "$d/.runner" ]; then echo "runner $i already set up"; continue; fi
  sudo -u runner mkdir -p "$d"
  sudo -u runner bash -c "cd $d && curl -fsSL -o r.tgz https://github.com/actions/runner/releases/download/v$VER/actions-runner-linux-$ARCH-$VER.tar.gz && tar xzf r.tgz && rm r.tgz"
  "$d/bin/installdependencies.sh" >/dev/null 2>&1 || true
  sudo -u runner bash -c "cd $d && ./config.sh --unattended --url https://github.com/etaram/commodity-feeder --token '$TOKEN' --name sinder-$i --labels sinder --replace" >/dev/null
  (cd "$d" && ./svc.sh install runner >/dev/null && ./svc.sh start >/dev/null)
  echo "runner $i started"
done
rm -f /opt/sinder/secrets/runner_reg.token
# the low-priority drop-in from runner-priority applies to every actions.runner.* unit; re-apply if present
systemctl daemon-reload
systemctl list-units --type=service --no-legend 'actions.runner.*' | awk '{print $1, $3, $4}'
ROOT
echo "registration token removed from the server"
