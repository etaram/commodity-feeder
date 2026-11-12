#!/usr/bin/env bash
# Runs as root on the server (called by deploy/ops/bench-semantic.sh, embed-universe.sh and semantic-status.sh through
# asroot). Semantic matching with open-source models on our own CPUs: no hosted model, no fee.
#   _semantic_root.sh bench  <repo checkout> <run id>   models scored on the TUNING half of the frozen evaluation
#   _semantic_root.sh embed  <repo checkout>            starts the overnight embedding of the whole supplier universe
#   _semantic_root.sh status <repo checkout>            progress counts of the embedding job
# Every model runs in a python:3.12-slim container at low priority (CPU shares 128, nice 19, idle I/O class) with at
# most 3.5 CPUs and 6 GB, so it uses idle capacity and yields to the database, the data gateway and the website; each
# container is removed when its step ends.
# Server folders (root only): /opt/sinder/semantic (packages, model files, universe text, vectors) and
# /opt/sinder/eval/<timestamp>/semantic (bench results). Bench results are also copied to Google Drive
# Sinder-Eval/<timestamp>/semantic.
# THE LOG IS PUBLIC: ids, counts, timings and metrics only. No request text, supplier name or evidence is printed.
set -euo pipefail
mode="$1"; repo="$2"
TS=20261111T181953Z
EV="/opt/sinder/eval/$TS"; OUT="$EV/semantic"; S=/opt/sinder/semantic
IMG=python:3.12-slim
IDS="Q05,Q06,Q07,Q08,Q09,Q13,Q14,Q15,Q19,Q20,Q24,Q25,Q26,Q27,Q30,Q31,Q33,Q34,Q35,Q37,Q39,Q40,T02,T03,T05,T07,T09,T10,T11,T12,T13,T14,T18,T19,T21,T23,T24,T27"
# low priority: the container may use all idle CPU (3.5 of 4) but yields to the database, gateway and website
LIMITS=(--cpus 3.5 --cpu-shares 128 --memory 6g --memory-swap 6g -e SEM_THREADS=4)
umask 077; mkdir -p "$S/models"; chmod 700 "$S"
[ -f "$repo/tools/semantic_rank.py" ] || { echo "repository checkout not found"; exit 1; }

run() { docker run --rm "${LIMITS[@]}" -e HF_HUB_DISABLE_TELEMETRY=1 -e PYTHONUNBUFFERED=1 -v "$S":/s -v "$repo":/w:ro "$@"; }

venv() {   # the packages, installed once into a virtual environment on the server
  if [ -x "$S/venv/bin/python" ] && run "$IMG" ionice -c 3 nice -n 19 /s/venv/bin/python -c "import fastembed, numpy, cryptography" >/dev/null 2>&1; then return 0; fi
  echo "installing fastembed (ONNX runtime), numpy and cryptography into $S/venv"
  rm -rf "$S/venv"
  run "$IMG" sh -c 'python -m venv /s/venv && /s/venv/bin/pip install -q --disable-pip-version-check fastembed==0.9.1 numpy cryptography 2>&1 | grep -iE "^error" | head -3; /s/venv/bin/python -c "import fastembed, onnxruntime; print(\"fastembed\", fastembed.__version__, \"onnxruntime\", onnxruntime.__version__)"'
}

universe() {   # decrypts the supplier index the app reads into one text line per company (root-only file)
  local src="" key_env="$S/.key.env"
  if docker volume inspect sinder_repo >/dev/null 2>&1; then src="vol"; fi
  grep -E '^WEB_INDEX_KEY=.+' /opt/sinder/repo/deploy/.env > "$key_env" 2>/dev/null || { rm -f "$key_env"; echo "WEB_INDEX_KEY is not in the server's deploy/.env: cannot read the supplier universe"; return 1; }
  chmod 600 "$key_env"
  if [ "$src" = vol ]; then
    echo "supplier index: read from the data service volume (the copy the app reads)"
    run --env-file "$key_env" -v sinder_repo:/repo:ro "$IMG" ionice -c 3 nice -n 19 /s/venv/bin/python /w/tools/semantic_rank.py universe --src /repo/data/web/suppliers.enc --out /s/universe.jsonl || { rm -f "$key_env"; return 1; }
  else
    echo "supplier index: data service volume not found, read from this checkout"
    run --env-file "$key_env" "$IMG" ionice -c 3 nice -n 19 /s/venv/bin/python /w/tools/semantic_rank.py universe --src /w/data/web/suppliers.enc --out /s/universe.jsonl || { rm -f "$key_env"; return 1; }
  fi
  rm -f "$key_env"
}

if [ "$mode" = bench ]; then
  rid="$3"; case "$rid" in *[!0-9]*|"") echo "bad run id"; exit 1;; esac
  [ -d "$EV" ] || { echo "no evaluation run with this timestamp on the server"; exit 1; }
  for f in rows.jsonl labels.jsonl; do [ -f "$EV/$f" ] || { echo "$f is missing in the run folder"; exit 1; }; done
  W="$S/work-$rid"; rm -rf "$W"; mkdir -p "$W"
  trap 'rm -rf "$W"; rm -f "$S/.key.env"' EXIT
  # only the tuning ids leave the evaluation folder; the held-out requests are never read
  python3 - "$EV" "$W" "$IDS" <<'PY'
import json, sys
src, dst, ids = sys.argv[1], sys.argv[2], set(sys.argv[3].split(","))
def lines(name):
    try:
        with open(f"{src}/{name}", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    yield json.loads(line)
    except FileNotFoundError:
        return
n = {}
for name in ("rows.jsonl", "labels.jsonl", "tenders.jsonl"):
    keep = [r for r in lines(name) if str(r.get("query_id") or "").strip() in ids]
    if name == "tenders.jsonl":
        keep = [{"query_id": r.get("query_id"), "stratum": r.get("stratum")} for r in keep]
    with open(f"{dst}/{name}", "w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    n[name] = len(keep)
print(f"fetched for the bench: {n['rows.jsonl']} result rows, {n['labels.jsonl']} label lines, {n['tenders.jsonl']} tender strata, for {len(ids)} tuning ids; nothing else left the folder")
PY
  venv
  if [ ! -s "$S/universe.jsonl" ] || [ -n "$(find "$S/universe.jsonl" -mmin +720 2>/dev/null)" ]; then universe || echo "continuing without the universe sample (throughput is then not measured)"; fi
  [ -f "$S/universe.jsonl.meta.json" ] && python3 -c "import json;m=json.load(open('$S/universe.jsonl.meta.json'));print('universe on the server:', m['written'], 'companies, mean text', m['mean_chars'], 'characters')"
  t0=$(date +%s)
  # smallest first; the job has 55 minutes, so a model is skipped once 30 minutes have gone
  for m in multilingual-e5-small bge-reranker-v2-m3-int8 paraphrase-multilingual-MiniLM-L12-v2 multilingual-e5-base Qwen3-Embedding-0.6B-int8 bge-reranker-v2-m3; do
    el=$(( $(date +%s) - t0 ))
    if [ "$el" -gt 1800 ]; then echo "== $m: skipped, time budget used ($el s)"; continue; fi
    timeout 600 docker run --rm --name semantic-bench "${LIMITS[@]}" -e HF_HUB_DISABLE_TELEMETRY=1 -e PYTHONUNBUFFERED=1 -v "$S":/s -v "$repo":/w:ro "$IMG" \
      ionice -c 3 nice -n 19 /s/venv/bin/python /w/tools/semantic_rank.py bench --data "/s/work-$rid" --model "$m" --cache /s/models --universe /s/universe.jsonl --sample 2000 2>/dev/null \
      || { echo "  the bench step ended with an error or hit 10 minutes for $m"; docker rm -f semantic-bench >/dev/null 2>&1 || true; }
  done
  echo "== host after the models"; free -m | sed -n 2p; uptime
  run "$IMG" ionice -c 3 nice -n 19 /s/venv/bin/python /w/tools/semantic_rank.py report --data "/s/work-$rid"
  mkdir -p "$OUT"; n=0
  for f in "$W"/summary.json "$W"/detail.jsonl "$W"/speed_*.json "$W"/scores_*.jsonl "$W"/error_*.txt; do [ -f "$f" ] && cp "$f" "$OUT/" && n=$((n+1)); done
  [ -f "$S/universe.jsonl.meta.json" ] && cp "$S/universe.jsonl.meta.json" "$OUT/universe_meta.json" && n=$((n+1))
  chmod -R go-rwx /opt/sinder/eval
  echo "kept on the server: $OUT ($n files)"
  if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
    if rclone copy "$OUT" "gdrive:Sinder-Eval/$TS/semantic" --quiet; then echo "copied to Google Drive: Sinder-Eval/$TS/semantic ($(rclone lsf "gdrive:Sinder-Eval/$TS/semantic" | wc -l) files there)"
    else echo "GOOGLE DRIVE COPY FAILED: the files are on the server only"; fi
  else echo "GOOGLE DRIVE NOT CONNECTED: the files are on the server only"; fi
  exit 0
fi

echo "unknown mode"; exit 1
