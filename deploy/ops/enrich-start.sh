#!/usr/bin/env bash
# Supplier enrichment job on the server: start (see deploy/enrich/_enrich_root.sh). The log is public: counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
. "$(dirname "$0")/_ch_key.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" start "$GITHUB_WORKSPACE"
