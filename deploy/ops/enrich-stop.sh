#!/usr/bin/env bash
# Supplier enrichment job on the server: stop (see deploy/enrich/_enrich_root.sh). The log is public: counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" stop "$GITHUB_WORKSPACE"
