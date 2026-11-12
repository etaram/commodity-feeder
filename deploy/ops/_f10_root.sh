#!/usr/bin/env bash
# Runs as root on the server (called by deploy/ops/bench-f10.sh through asroot). Three steps around benchmark F10:
#   _f10_root.sh fetch <timestamp> <work directory> <uid of the runner user> <ids, comma separated>
#       writes into the work directory ONLY the lines of the given tender ids (the tuning half): their rows of
#       tenders.jsonl and their stratum lines (rank 0) of labels.jsonl. The held-out tenders never leave the folder.
#       Also hands over f10/gemini_state.json if an earlier run left one (answers already paid for with a request, and
#       the count of requests sent to Google).
#   _f10_root.sh state <timestamp> <work directory>
#       puts gemini_state.json back at once, so the request count survives a run that dies later.
#   _f10_root.sh store <timestamp> <work directory>
#       keeps detail.jsonl, summary.json and gemini_state.json in /opt/sinder/eval/<timestamp>/f10/ and copies them to
#       Google Drive Sinder-Eval/<timestamp>/f10.
# THE LOG IS PUBLIC: file names and line counts only.
set -euo pipefail
mode="$1"; ts="$2"; work="$3"; dir="/opt/sinder/eval/$ts"; out="$dir/f10"
case "$ts" in *[!0-9TZ]*|"") echo "bad timestamp"; exit 1;; esac
[ -d "$dir" ] || { echo "no evaluation run with this timestamp on the server"; exit 1; }
[ -d "$work" ] || { echo "work directory is missing"; exit 1; }
umask 077

if [ "$mode" = fetch ]; then
  uid="$4"; ids="$5"
  case "$ids" in *[!T0-9,]*|"") echo "bad id list"; exit 1;; esac
  for f in tenders.jsonl labels.jsonl; do [ -f "$dir/$f" ] || { echo "$f is missing in the run folder"; exit 1; }; done
  python3 - "$dir" "$work" "$ids" <<'PY'
import json, sys
src, dst, ids = sys.argv[1], sys.argv[2], set(sys.argv[3].split(","))
def lines(name):
    with open(f"{src}/{name}", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)
t = [r for r in lines("tenders.jsonl") if str(r.get("query_id") or "") in ids]
def zero(x):
    try: return int(x or 0) == 0
    except (TypeError, ValueError): return False
l = [{"query_id": str(r.get("query_id")).strip(), "rank": 0, "label": r.get("label")} for r in lines("labels.jsonl")
     if str(r.get("query_id") or "").strip() in ids and zero(r.get("rank")) and str(r.get("label") or "").strip().lower().replace(" ", "_") in ("goods", "non_goods", "mixed")]
for name, rows in (("tenders.jsonl", t), ("labels.jsonl", l)):
    with open(f"{dst}/{name}", "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
print(f"fetched for the benchmark: {len(t)} tender rows and {len(l)} stratum lines, for {len(ids)} tuning ids asked; nothing else left the folder")
PY
  [ -f "$out/gemini_state.json" ] && cp "$out/gemini_state.json" "$work/gemini_state.json" && echo "an earlier run left its Google request count and answers: handed over"
  chown -R "$uid" "$work"; chmod -R u+rwX,go-rwx "$work"
  exit 0
fi

mkdir -p "$out"
if [ "$mode" = state ]; then
  [ -f "$work/gemini_state.json" ] && cp "$work/gemini_state.json" "$out/gemini_state.json" && echo "Google request count kept on the server"
  chmod -R go-rwx "$out"; exit 0
fi

[ "$mode" = store ] || { echo "unknown mode"; exit 1; }
n=0
for f in detail.jsonl summary.json gemini_state.json; do [ -f "$work/$f" ] && cp "$work/$f" "$out/$f" && n=$((n+1)); done
chmod -R go-rwx /opt/sinder/eval
echo "kept on the server: $out ($n files; detail lines $([ -f "$out/detail.jsonl" ] && wc -l < "$out/detail.jsonl" || echo 0))"
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  ok=1
  for f in detail.jsonl summary.json; do [ -f "$out/$f" ] || continue; rclone copy "$out/$f" "gdrive:Sinder-Eval/$ts/f10" --quiet || ok=0; done
  if [ "$ok" = 1 ]; then echo "copied to Google Drive: Sinder-Eval/$ts/f10 ($(rclone lsf "gdrive:Sinder-Eval/$ts/f10" | wc -l) files there)"
  else echo "GOOGLE DRIVE COPY FAILED: the files are on the server only ($out)"; exit 1; fi
else echo "GOOGLE DRIVE NOT CONNECTED: the files are on the server only ($out)"; exit 1; fi
