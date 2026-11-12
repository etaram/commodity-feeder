#!/usr/bin/env bash
# Builds and (re)starts the check-now worker on the server (leads/check_now.py, service checknow in
# deploy/docker-compose.server.prod.yml): "check the website" in the panel is answered within about a minute.
# server-up also starts it (it recreates every service of the production overlay). Status lines only, no secrets.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
instance_run _checknow_root.sh
