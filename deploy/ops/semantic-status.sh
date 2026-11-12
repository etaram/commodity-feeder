#!/usr/bin/env bash
# Progress of the supplier embedding job: parts done, vectors embedded, rate. Counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_semantic_root.sh" status "$GITHUB_WORKSPACE"
