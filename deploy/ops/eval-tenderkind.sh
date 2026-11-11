#!/usr/bin/env bash
# Scores the tender goods / non-goods classifier (dealdesk/lib/tenderkind.ts) against the blind labeller's strata, on
# the TUNING half of the frozen split only. Prints a numeric matrix; no titles (the log is public).
set -euo pipefail
. "$(dirname "$0")/_root.sh"
W="$RUNNER_TEMP/tk-$GITHUB_RUN_ID"; mkdir -p "$W"; trap 'rm -rf "$W"' EXIT
asroot sh -c "ts=\$(ls -1 /opt/sinder/eval | sort | tail -1); cp /opt/sinder/eval/\$ts/tenders.jsonl /opt/sinder/eval/\$ts/labels.jsonl '$W/' && chown -R $(id -u) '$W' && echo run \$ts"
IDS="T02,T03,T05,T07,T09,T10,T11,T12,T13,T14,T18,T19,T21,T23,T24,T27"
docker run --rm -v "$GITHUB_WORKSPACE":/w:ro -v "$W":/d:ro -w /w/dealdesk node:22-alpine sh -c \
  "npx --yes esbuild@0.24.0 tools/eval-tenderkind.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=/tmp/tk.js --log-level=error && node /tmp/tk.js /d/tenders.jsonl /d/labels.jsonl --ids $IDS"
