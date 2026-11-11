#!/usr/bin/env bash
# Runs as root on the server (called by the supplier-label workflow through asroot). Two steps around the blind labeller:
#   _label_root.sh fetch <timestamp> <work directory> <uid of the runner user>
#       copies rows.jsonl and tenders.jsonl of /opt/sinder/eval/<timestamp>/ into the work directory, plus labels.jsonl
#       if an earlier run left one (the labeller resumes from it). Nothing else leaves the folder: the matcher's
#       verdicts stay where the labeller cannot read them.
#   _label_root.sh store <timestamp> <work directory> <repository checkout>
#       puts labels.jsonl back, scores it with tools/eval_score.py (now the verdicts are read, the labelling is over),
#       writes score.txt and score.json beside it, copies the three files to Google Drive Sinder-Eval/<timestamp>/
#       and prints aggregate numbers.
# THE LOG IS PUBLIC: this script prints counts and percentages only. The scorer's own output names companies, so all of
# it goes to the files; the numbers shown are picked from score.json by key, and only if they are numbers.
set -euo pipefail
mode="$1"; ts="$2"; work="$3"; dir="/opt/sinder/eval/$ts"
case "$ts" in *[!0-9TZ]*|"") echo "bad timestamp"; exit 1;; esac
[ -d "$dir" ] || { echo "no evaluation run with this timestamp on the server"; exit 1; }
[ -d "$work" ] || { echo "work directory is missing"; exit 1; }
umask 077

if [ "$mode" = fetch ]; then
  uid="$4"
  [ -f "$dir/rows.jsonl" ] || { echo "rows.jsonl is missing in the run folder"; exit 1; }
  for f in rows.jsonl tenders.jsonl labels.jsonl; do
    [ -f "$dir/$f" ] || continue
    cp "$dir/$f" "$work/$f"; chown "$uid" "$work/$f"; chmod 600 "$work/$f"
  done
  echo "fetched for the labeller: rows $(wc -l < "$work/rows.jsonl"), tenders $([ -f "$work/tenders.jsonl" ] && wc -l < "$work/tenders.jsonl" || echo 0), labels from an earlier run $([ -f "$work/labels.jsonl" ] && wc -l < "$work/labels.jsonl" || echo 0)"
  exit 0
fi

[ "$mode" = store ] || { echo "unknown mode"; exit 1; }
repo="$4"
[ -s "$work/labels.jsonl" ] || { echo "the labeller wrote no labels: nothing stored"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "python3 is not installed on the server: labels not scored"; cp "$work/labels.jsonl" "$dir/labels.jsonl"; exit 1; }
cp "$work/labels.jsonl" "$dir/labels.jsonl"
args=("$dir/rows.jsonl" "$dir/verdicts.jsonl" "$dir/labels.jsonl")
[ -f "$dir/tenders.jsonl" ] && args+=(--tenders "$dir/tenders.jsonl")
[ -f "$dir/summary.json" ] && args+=(--summary "$dir/summary.json")
[ -f "$dir/human_labels.jsonl" ] && args+=(--human "$dir/human_labels.jsonl")   # today the owner's verdicts are on Google Drive only
python3 "$repo/tools/eval_score.py" "${args[@]}" > "$dir/score.txt" 2>&1 || { echo "the scorer failed (its message is in score.txt on the server)"; exit 1; }
python3 "$repo/tools/eval_score.py" "${args[@]}" --json > "$dir/score.json" 2>/dev/null || { echo "the scorer failed on the JSON output"; exit 1; }
chmod -R go-rwx /opt/sinder/eval
echo "stored on the server: labels.jsonl ($(wc -l < "$dir/labels.jsonl") lines), score.txt, score.json"

# aggregate numbers only: every value is printed through num(), which lets nothing but a number through
python3 - "$dir/score.json" "$dir/labels.jsonl" <<'PY'
import json, sys
from collections import Counter
res = json.load(open(sys.argv[1], encoding="utf-8"))
num = lambda x: x if isinstance(x, (int, float)) and not isinstance(x, bool) else "n/a"
pct = lambda x: f"{100 * x:.1f}%" if isinstance(x, (int, float)) and not isinstance(x, bool) else "n/a"
for name in ("product", "tender"):
    s = res.get(name)
    if not isinstance(s, dict):
        continue
    print(f"{name} set: requests {num(s.get('requests'))}, rows {num(s.get('rows'))}, labelled_rows {num(s.get('labelled_rows'))}")
    for k in ("5", "10", "25"):
        p = (s.get("pooled") or {}).get(k) or {}
        print(f"  precision at {k}: pooled {pct(p.get('precision'))} (relevant {num(p.get('relevant'))}, partly {num(p.get('partly'))}, irrelevant {num(p.get('irrelevant'))}, "
              f"cannot_tell {num(p.get('cannot_tell'))}, unlabelled {num(p.get('unlabelled'))}, judged {num(p.get('judged'))}); precision_with_partly {pct(p.get('precision_with_partly'))}; "
              f"macro (mean over requests) {pct((s.get('macro') or {}).get(k))}")
    print(f"  share_no_relevant_in_top10: {pct(s.get('share_no_relevant_in_top10'))} (requests_with_no_relevant_in_top10 {num(s.get('requests_with_no_relevant_in_top10'))} "
          f"of requests_decided_for_top10 {num(s.get('requests_decided_for_top10'))}; requests_with_no_rows {num(s.get('requests_with_no_rows'))})")
    print(f"  false_positives_total: {num(s.get('false_positives_total'))}")
    for b in ("supported", "plausible", "related", "none"):   # fixed names: a bucket name from the file is never printed
        p = (s.get("per_bucket") or {}).get(b)
        if isinstance(p, dict):
            print(f"  per_bucket {b}: precision {pct(p.get('precision'))} (relevant {num(p.get('relevant'))} of judged {num(p.get('judged'))})")
    if "non_goods_tenders" in s:
        print(f"  non_goods_tenders {num(s.get('non_goods_tenders'))}, non_goods_tenders_with_any_supplier {num(s.get('non_goods_tenders_with_any_supplier'))} "
              f"(share_non_goods_with_any_supplier {pct(s.get('share_non_goods_with_any_supplier'))}), non_goods_rows_returned {num(s.get('non_goods_rows_returned'))}")
        for st in ("goods", "non_goods", "mixed"):
            p = ((s.get("per_stratum") or {}).get(st) or {}).get("10") or {}
            print(f"  per_stratum {st} precision at 10: {pct(p.get('precision'))} (judged {num(p.get('judged'))})")
allowed = ("relevant", "partly", "irrelevant", "cannot_tell", "goods", "non_goods", "mixed")
c, rows = Counter(), 0
for line in open(sys.argv[2], encoding="utf-8"):
    if line.strip():
        x = json.loads(line)
        zero = x.get("rank") == 0
        rows += not zero
        lab = x.get("label")
        c[("tender buys " if zero else "") + (lab if lab in allowed else "other")] += 1
print(f"labelled rows in labels.jsonl: {rows}")
print("labels: " + ", ".join(f"{k} {v}" for k, v in sorted(c.items())))
PY

if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  ok=1
  for f in labels.jsonl score.txt score.json; do rclone copy "$dir/$f" "gdrive:Sinder-Eval/$ts" --quiet || ok=0; done
  if [ "$ok" = 1 ]; then echo "copied to Google Drive: Sinder-Eval/$ts ($(rclone lsf "gdrive:Sinder-Eval/$ts" | wc -l) files there)"
  else echo "GOOGLE DRIVE COPY FAILED: the files are on the server only ($dir)"; exit 1; fi
else echo "GOOGLE DRIVE NOT CONNECTED: the files are on the server only ($dir)"; exit 1; fi
