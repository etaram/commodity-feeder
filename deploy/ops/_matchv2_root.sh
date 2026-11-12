#!/usr/bin/env bash
# Runs as root on the server (called by deploy/ops/match-v2-tune.sh and match-v2-final.sh through asroot). Three steps
# around the supplier-matching v2 measurement (dealdesk/tools/eval-matchv2.ts):
#   _matchv2_root.sh fetch <timestamp> <work directory> <uid of the runner user> <tune|final>
#       writes into the work directory ONLY the lines of one half of the frozen split (split_manifest.json): rows,
#       labels, tenders and verdicts of those request ids, and ids.txt. The other half never leaves the folder.
#       Also hands over matchv2/gemini_state.json (answers already paid for and the call count of this task) and, for
#       the tuning half, f10_seed.json: benchmark F10's answers to the same tender-kind question.
#       The final half is handed over once only: after a final run has reported, a second one is refused.
#   _matchv2_root.sh state <timestamp> <work directory>
#       puts gemini_state.json back at once (the call count survives a run that dies later), and records that the
#       final check has reported, if it has.
#   _matchv2_root.sh store <timestamp> <work directory>
#       keeps detail_*.jsonl and summary_*.json in /opt/sinder/eval/<timestamp>/matchv2/ and copies them to Google Drive
#       Sinder-Eval/<timestamp>/matchv2.
# THE LOG IS PUBLIC: file names, ids and line counts only.
set -euo pipefail
mode="$1"; ts="$2"; work="$3"; dir="/opt/sinder/eval/$ts"; out="$dir/matchv2"
case "$ts" in *[!0-9TZ]*|"") echo "bad timestamp"; exit 1;; esac
[ -d "$dir" ] || { echo "no evaluation run with this timestamp on the server"; exit 1; }
[ -d "$work" ] || { echo "work directory is missing"; exit 1; }
umask 077
TUNE="Q05 Q06 Q07 Q08 Q09 Q13 Q14 Q15 Q19 Q20 Q24 Q25 Q26 Q27 Q30 Q31 Q33 Q34 Q35 Q37 Q39 Q40 T02 T03 T05 T07 T09 T10 T11 T12 T13 T14 T18 T19 T21 T23 T24 T27"

if [ "$mode" = fetch ]; then
  uid="$4"; half="$5"
  case "$half" in tune|final) ;; *) echo "bad half"; exit 1;; esac
  if [ "$half" = final ] && [ -f "$out/final_reported" ]; then echo "the final check has already reported once: refused"; exit 1; fi
  for f in rows.jsonl labels.jsonl tenders.jsonl verdicts.jsonl split_manifest.json; do [ -f "$dir/$f" ] || { echo "$f is missing in the run folder"; exit 1; }; done
  python3 - "$dir" "$work" "$half" "$TUNE" <<'PY'
import json, sys
src, dst, half, tune = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4].split()
man = json.load(open(f"{src}/split_manifest.json"))
if sorted(man["tune"]) != sorted(tune) or set(man["tune"]) & set(man["heldout"]):
    sys.exit("the split manifest does not match the tuning ids of this task: stopped")
ids = set(man["tune"] if half == "tune" else man["heldout"])
def lines(name):
    with open(f"{src}/{name}", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)
counts = {}
for name in ("rows.jsonl", "labels.jsonl", "tenders.jsonl", "verdicts.jsonl"):
    keep = [r for r in lines(name) if str(r.get("query_id") or "").strip() in ids]
    with open(f"{dst}/{name}", "w", encoding="utf-8") as f:
        for r in keep:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    counts[name] = len(keep)
open(f"{dst}/ids.txt", "w").write(",".join(sorted(ids)) + "\n")
print(f"fetched the {half} half: {len(ids)} request ids; lines " + ", ".join(f"{k} {v}" for k, v in counts.items()) + "; nothing of the other half left the folder")
PY
  [ -f "$out/gemini_state.json" ] && cp "$out/gemini_state.json" "$work/gemini_state.json" && echo "an earlier run left its Google answers and call count: handed over"
  if [ "$half" = tune ] && [ -f "$dir/f10/gemini_state.json" ]; then
    python3 - "$dir/f10/gemini_state.json" "$work/f10_seed.json" "$TUNE" <<'PY'
import json, sys
st, tune = json.load(open(sys.argv[1])), set(sys.argv[3].split())
seed = {k: v["answer"] for k, v in (st.get("answers") or {}).items() if k in tune and isinstance(v, dict) and v.get("answer") in ("goods", "non_goods", "mixed")}
json.dump(seed, open(sys.argv[2], "w"))
print(f"benchmark F10 tender-kind answers handed over for {len(seed)} tuning tenders (no new call needed for them)")
PY
  fi
  chown -R "$uid" "$work"; chmod -R u+rwX,go-rwx "$work"
  exit 0
fi

mkdir -p "$out"
if [ "$mode" = state ]; then
  [ -f "$work/gemini_state.json" ] && cp "$work/gemini_state.json" "$out/gemini_state.json" && echo "Google answers and call count kept on the server"
  [ -f "$work/final_reported" ] && cp "$work/final_reported" "$out/final_reported" && echo "final check recorded as reported: it cannot run again"
  chmod -R go-rwx "$out"; exit 0
fi

[ "$mode" = store ] || { echo "unknown mode"; exit 1; }
n=0
for f in "$work"/detail_*.jsonl "$work"/summary_*.json; do [ -f "$f" ] && cp "$f" "$out/" && n=$((n+1)); done
chmod -R go-rwx /opt/sinder/eval
echo "kept on the server: $out ($n result files)"
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  ok=1
  for f in "$out"/detail_*.jsonl "$out"/summary_*.json; do [ -f "$f" ] || continue; rclone copy "$f" "gdrive:Sinder-Eval/$ts/matchv2" --quiet || ok=0; done
  if [ "$ok" = 1 ]; then echo "copied to Google Drive: Sinder-Eval/$ts/matchv2 ($(rclone lsf "gdrive:Sinder-Eval/$ts/matchv2" | wc -l) files there)"
  else echo "GOOGLE DRIVE COPY FAILED: the files are on the server only ($out)"; exit 1; fi
else echo "GOOGLE DRIVE NOT CONNECTED: the files are on the server only ($out)"; exit 1; fi
