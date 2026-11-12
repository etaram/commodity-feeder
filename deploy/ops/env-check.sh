#!/usr/bin/env bash
# Read-only inventory for the server instance: which keys of deploy/env.example are set in the server's .env (names
# only, never values), open ports, firewall rules for 80/443, last database backup. Prints no secrets.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
instance_run _env_check_root.sh
