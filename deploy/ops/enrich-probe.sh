#!/usr/bin/env bash
# Read-only look at what the supplier enrichment job can use on this server (counts and versions only; the log is public).
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" probe "$GITHUB_WORKSPACE"
