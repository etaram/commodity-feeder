#!/usr/bin/env bash
# Builds and starts the Deal Desk as a second instance on the server (compose project sinder-server), behind the data
# gateway's Caddy on an sslip.io address. Database backup first when the last one is older than 6 hours. Prints only
# status lines, no secrets. See deploy/docker-compose.server.yml.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
instance_run _server_up_root.sh

echo "== screen check after server-up"
bash "$(dirname "$0")/screen-check.sh"
