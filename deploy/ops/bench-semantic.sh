#!/usr/bin/env bash
# Semantic matching on our own CPU server (no hosted model, no fee): open-source embedding models and a cross-encoder
# reranker re-order the already-labelled result rows of the TUNING half of the frozen evaluation. Prints ids, counts,
# timings and metrics only (the log is public); row detail stays on the server and goes to Google Drive.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
. "$(dirname "$0")/_semantic_key.sh"
asroot env SEM_KEYFILE="$KEYF" bash "$GITHUB_WORKSPACE/deploy/ops/_semantic_root.sh" bench "$GITHUB_WORKSPACE" "$GITHUB_RUN_ID"
