#!/usr/bin/env bash
# Supplier enrichment job on the server: the registry people lane's measurement sample (see deploy/enrich/_enrich_root.sh).
# The log is public: counts only; the hand-check file is printed only sealed to the reviewer's key.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
. "$(dirname "$0")/_ch_key.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/enrich/_enrich_root.sh" people "$GITHUB_WORKSPACE"
