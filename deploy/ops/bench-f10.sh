#!/usr/bin/env bash
# Benchmark F10: three classifiers on one task, TENDER KIND (goods / non_goods / mixed), on the TUNING half of the
# frozen split only (16 tenders). A = the rule classifier (dealdesk/lib/tenderkind.ts), B = a small local model in an
# Ollama container limited to 3 CPUs and 6 GB as in bench-llm.sh, C = Google's Decisions API (gemini-decision-1; key
# from the repository secret GEMINI_API_KEY, at most 20 requests over all runs). No other paid call.
# THE LOG IS PUBLIC: ids, counts and metrics only. Row-level detail goes to /opt/sinder/eval/<stamp>/f10/ and to
# Google Drive Sinder-Eval/<stamp>/f10. The bench container is removed at the end; model files stay in the volume.
set -uo pipefail
. "$(dirname "$0")/_root.sh"
TS=20261111T181953Z
IDS="T02,T03,T05,T07,T09,T10,T11,T12,T13,T14,T18,T19,T21,T23,T24,T27"
TOOL=/w/tools/bench_tenderkind_models.py
W="$RUNNER_TEMP/f10-$GITHUB_RUN_ID"; rm -rf "$W"; mkdir -m 700 "$W"
trap 'docker rm -f ollama-bench >/dev/null 2>&1; rm -rf "$W"' EXIT
py() { docker run --rm "$@"; }

asroot bash "$GITHUB_WORKSPACE/deploy/ops/_f10_root.sh" fetch "$TS" "$W" "$(id -u)" "$IDS" || { echo "fetch failed"; exit 1; }

echo "== A. rules"
docker run --rm -v "$GITHUB_WORKSPACE":/w:ro -v "$W":/d -w /w/dealdesk node:22-alpine sh -c \
  "npx --yes esbuild@0.24.0 tools/eval-tenderkind.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=/tmp/tk.js --log-level=error && node /tmp/tk.js /d/tenders.jsonl /d/labels.jsonl --ids $IDS --jsonl=/d/rules.jsonl" \
  || echo "the rules step failed"

echo "== C. Gemini Decisions API"
py -e GEMINI_API_KEY -v "$GITHUB_WORKSPACE":/w:ro -v "$W":/d python:3.12-alpine python3 "$TOOL" gemini --data /d || echo "the gemini step failed"
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_f10_root.sh" state "$TS" "$W" || true

# one fresh container per model, so the container's memory peak belongs to that model alone
local_model() {   # <model> <pull allowed: 0|1>
  local m="$1" pull="$2" slug; slug=$(printf %s "$m" | tr 'A-Z' 'a-z' | sed 's/[^a-z0-9]\+/_/g; s/^_//; s/_$//')
  echo "== B. local model $m"
  docker rm -f ollama-bench >/dev/null 2>&1
  docker run -d --name ollama-bench --cpus 3 --memory 6g -v ollama:/root/.ollama ollama/ollama >/dev/null || { printf '%s\nthe bench container did not start\n' "$m" > "$W/local_$slug.skipped"; return; }
  for i in $(seq 1 30); do docker exec ollama-bench ollama list >/dev/null 2>&1 && break; sleep 2; done
  if ! docker exec ollama-bench ollama list 2>/dev/null | awk '{print $1}' | grep -qx "$m"; then
    if [ "$pull" != 1 ]; then echo "$m is not in the volume"; printf '%s\nthe model is not in the ollama volume\n' "$m" > "$W/local_$slug.skipped"; docker rm -f ollama-bench >/dev/null; return; fi
    t0=$(date +%s)
    if timeout 300 docker exec ollama-bench ollama pull "$m" >/dev/null 2>&1; then echo "pulled $m in $(( $(date +%s)-t0 )) s"
    else rc=$?; echo "pull of $m did not finish within 5 minutes (exit $rc): skipped"
      printf '%s\nthe pull did not finish within 5 minutes (exit %s after %s s), so the model was skipped\n' "$m" "$rc" "$(( $(date +%s)-t0 ))" > "$W/local_$slug.skipped"
      docker rm -f ollama-bench >/dev/null; return; fi
  fi
  py --network container:ollama-bench -v "$GITHUB_WORKSPACE":/w:ro -v "$W":/d python:3.12-alpine python3 "$TOOL" local --data /d --model "$m" || echo "the local step failed for $m"
  docker exec ollama-bench sh -c 'cat /sys/fs/cgroup/memory.peak 2>/dev/null || cat /sys/fs/cgroup/memory/memory.max_usage_in_bytes 2>/dev/null' > "$W/local_$slug.mem" 2>/dev/null
  docker stats --no-stream --format 'container now: memory {{.MemUsage}} cpu {{.CPUPerc}}' ollama-bench
  docker rm -f ollama-bench >/dev/null
}
local_model qwen3:1.7b 0
local_model qwen3:4b 1
echo "== host after the local models"; free -h | sed -n 2p; uptime

py -v "$GITHUB_WORKSPACE":/w:ro -v "$W":/d python:3.12-alpine python3 "$TOOL" report --data /d; rc=$?
asroot bash "$GITHUB_WORKSPACE/deploy/ops/_f10_root.sh" store "$TS" "$W" || rc=1
echo "bench container removed (model files kept in the ollama volume)"
exit $rc
