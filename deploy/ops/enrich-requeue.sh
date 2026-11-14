#!/usr/bin/env bash
# Rebuild the enrichment queue from the current supplier index and restart the enrichment run (see deploy/enrich/_enrich_root.sh requeue).
# Keys already read are skipped. The log is public: counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
. "$(dirname "$0")/_ch_key.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" requeue "$GITHUB_WORKSPACE"
