#!/usr/bin/env bash
# Adds GitHub Actions runners on this server so the data workflows run here (no time limits, private cache on disk).
#   bash runners.sh 3
# It asks for a registration token: GitHub > the repository > Settings > Actions > Runners > New self-hosted runner
# shows it (valid for one hour). Type it here on the server; do not send it to anyone.
set -euo pipefail
N="${1:-3}"
[ "$(id -u)" = 0 ] || { echo "run as root"; exit 1; }
read -r -s -p "Registration token: " TOKEN; echo
id runner >/dev/null 2>&1 || useradd -m -s /bin/bash runner
echo "runner ALL=(ALL) NOPASSWD: /usr/bin/apt-get" > /etc/sudoers.d/runner   # media.yml installs ffmpeg with apt-get
VER=$(curl -fsS https://api.github.com/repos/actions/runner/releases/latest | jq -r .tag_name | sed 's/^v//')
ARCH=$(uname -m | sed 's/x86_64/x64/; s/aarch64/arm64/')
for i in $(seq 1 "$N"); do
  d=/home/runner/r$i
  [ -f "$d/.runner" ] && { echo "runner $i already set up"; continue; }
  sudo -u runner mkdir -p "$d"
  sudo -u runner bash -c "cd $d && curl -fsSL -o r.tgz https://github.com/actions/runner/releases/download/v$VER/actions-runner-linux-$ARCH-$VER.tar.gz && tar xzf r.tgz && rm r.tgz"
  "$d/bin/installdependencies.sh" >/dev/null
  sudo -u runner bash -c "cd $d && ./config.sh --unattended --url https://github.com/etaram/commodity-feeder --token '$TOKEN' --name sinder-$i --labels sinder --replace"
  (cd "$d" && ./svc.sh install runner >/dev/null && ./svc.sh start >/dev/null)
  echo "runner $i started"
done
echo "Runners are up. To move the workflows here: GitHub > Settings > Secrets and variables > Actions > Variables > new variable RUNNER_LABEL = sinder"
echo "To move them back to GitHub's machines: delete that variable."
