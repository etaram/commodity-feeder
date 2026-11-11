#!/usr/bin/env bash
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot sh -c 'cd /opt/sinder/repo && git pull -q && bash deploy/ops/_gateway_root.sh'
