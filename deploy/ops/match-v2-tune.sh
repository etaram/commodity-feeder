#!/usr/bin/env bash
# Supplier matching v2 on the TUNING half of the frozen split (dealdesk/tools/eval-matchv2.ts): baseline, A (tender
# kind routing), B (fit re-rank) and A+B, on the labelled rows the search already returned. Google's
# gemini-decision-1 (key: repository secret GEMINI_API_KEY, passed to this task only) is called at most RUN_CAP times
# in this run and 60 times over the whole task; every answer is kept on the server and never bought twice.
# THE LOG IS PUBLIC: ids, counts and metrics only. Detail goes to /opt/sinder/eval/<stamp>/matchv2/ and Google Drive.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
TS=20261111T181953Z
HALF="${MATCHV2_HALF:-tune}"
RUN_CAP="${MATCHV2_RUN_CAP:-25}"
TIEBREAK="${MATCHV2_TIEBREAK:-off}"
W="$RUNNER_TEMP/m2-$GITHUB_RUN_ID"; rm -rf "$W"; mkdir -m 700 "$W"
trap 'rm -rf "$W"' EXIT

asroot bash "$GITHUB_WORKSPACE/deploy/ops/_matchv2_root.sh" fetch "$TS" "$W" "$(id -u)" "$HALF" || { echo "fetch failed"; exit 1; }
docker run --rm -e GEMINI_API_KEY -v "$GITHUB_WORKSPACE":/w:ro -v "$W":/d -w /w/dealdesk node:22-alpine sh -c \
  "npx --yes esbuild@0.24.0 tools/eval-matchv2.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=/tmp/m2.js --log-level=error && node /tmp/m2.js --data /d --phase $HALF --tiebreak $TIEBREAK --run-cap $RUN_CAP --task-cap 60"
rc=$?
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_matchv2_root.sh" state "$TS" "$W" || rc=1
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_matchv2_root.sh" store "$TS" "$W" || rc=1
exit $rc
