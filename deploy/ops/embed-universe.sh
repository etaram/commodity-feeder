#!/usr/bin/env bash
# Starts the overnight embedding of the whole supplier universe on our own CPUs (detached container semantic-embed,
# low priority, at most 3.5 CPUs and 6 GB, removed when done, resumable: a second start continues from the last finished
# part). Estimates the time from the throughput the bench measured; above 12 hours it embeds the completed records
# (product description or official website) first. Prints counts only.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_semantic_root.sh" embed "$GITHUB_WORKSPACE"
