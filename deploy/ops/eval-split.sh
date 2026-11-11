#!/usr/bin/env bash
# Freezes the tuning / held-out split of the supplier-match evaluation and prints the baseline of each half.
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_split_root.sh" "$GITHUB_WORKSPACE"
