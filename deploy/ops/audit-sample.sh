#!/usr/bin/env bash
# Draws the blind audit sample of the latest supplier-match evaluation and copies it to Google Drive. Counts only in the log.
. "$(dirname "$0")/_root.sh"
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_audit_root.sh"
