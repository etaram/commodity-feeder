#!/usr/bin/env bash
# Probe the public tender sources listed in deploy/ops/probe/urls.txt from the server (shape only, short output).
set -euo pipefail
python3 -I "$(dirname "$0")/probe/probe.py" "$(dirname "$0")/probe/urls.txt"
