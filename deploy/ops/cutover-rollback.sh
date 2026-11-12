#!/usr/bin/env bash
# Returns the server instance to the isolated test mode (deploy/CUTOVER.md, rollback). Run after the owner has put the
# desk.sinder.pro CNAME back to Vercel. Never touches Vercel or DNS. Prints no secret.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
instance_run _cutover_rollback_root.sh
