#!/usr/bin/env bash
# Puts the server instance into PRODUCTION mode for desk.sinder.pro (deploy/CUTOVER.md). Run ONLY after the owner has
# changed DNS: the script checks public DNS first and refuses (changing nothing) unless desk.sinder.pro resolves to
# 216.158.234.218. Never touches Vercel or DNS. Prints names, statuses and hosts only, never a secret.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
instance_run _cutover_switch_root.sh

echo "== screen check after cutover-switch"
bash "$(dirname "$0")/screen-check.sh"
