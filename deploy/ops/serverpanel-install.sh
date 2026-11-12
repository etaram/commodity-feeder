#!/usr/bin/env bash
# Installs or updates the server status feed of the admin panel ("Server and tasks"):
#   sinder-serverpanel.timer   every 2 minutes, low priority: deploy/ops/serverpanel/collect.py writes
#                              /opt/sinder/serverpanel/public/status.json and history.json (no secrets, no personal data)
#   data service               serves that folder read-only at http://data:8080/_server/ (deploy/docker-compose.yml);
#                              the repository checkout is not written to. Reached from the internet only through the
#                              data gateway's secret path, like every other data file.
# Then checks from inside the docker network that the app's path answers, and prints only sizes and key names.
set -euo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/ops/serverpanel/_install_root.sh" "$GITHUB_WORKSPACE"
