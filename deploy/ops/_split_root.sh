#!/usr/bin/env bash
# Runs as root on the server: freezes the tuning / held-out split of the latest labelled evaluation run (once) and
# prints the baseline of each half. Numbers and request ids only: the log is public.
set -euo pipefail
repo="$1"; ts="$(ls -1 /opt/sinder/eval 2>/dev/null | sort | tail -1)"; dir="/opt/sinder/eval/$ts"
[ -f "$dir/score.json" ] && [ -f "$dir/labels.jsonl" ] || { echo "no labelled and scored run found"; exit 1; }
umask 077
python3 "$repo/tools/eval_split.py" "$dir/score.json" "$dir/labels.jsonl" "$repo/dealdesk/lib/evalqueries.ts" "$dir/split_manifest.json"
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  rclone copy "$dir/split_manifest.json" "gdrive:Sinder-Eval/$ts" --quiet && echo "split_manifest.json copied to Google Drive: Sinder-Eval/$ts" || echo "the copy to Google Drive failed"
fi
