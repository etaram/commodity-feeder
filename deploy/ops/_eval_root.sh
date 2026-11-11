#!/usr/bin/env bash
# Runs as root on the server (called by the supplier-eval workflow through asroot). Keeps the blind supplier-match
# evaluation on the server (root only) and copies it to the owner's Google Drive, folder Sinder-Eval/<timestamp>/
# (rclone remote "gdrive"; its scope reaches only folders this tool creates, so the folder is created here).
# The owner's own verdicts (human_labels.jsonl) go to Google Drive only. Prints file names and line counts, never content.
#   _eval_root.sh <directory that holds the output files> <timestamp>
set -euo pipefail
src="$1"; ts="$2"; dst="/opt/sinder/eval/$ts"
case "$ts" in *[!0-9TZ]*|"") echo "bad timestamp"; exit 1;; esac
for f in rows.jsonl verdicts.jsonl summary.json; do [ -f "$src/$f" ] || { echo "missing output file: $f"; exit 1; }; done
umask 077; mkdir -p "$dst"
for f in rows.jsonl verdicts.jsonl tenders.jsonl summary.json; do [ -f "$src/$f" ] && cp "$src/$f" "$dst/$f"; done
chmod -R go-rwx /opt/sinder/eval
echo "kept on the server: $dst ($(ls -1 "$dst" | wc -l) files; rows $(wc -l < "$dst/rows.jsonl"), verdicts $(wc -l < "$dst/verdicts.jsonl"))"
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  ok=1
  for f in rows.jsonl verdicts.jsonl tenders.jsonl summary.json human_labels.jsonl; do
    [ -f "$src/$f" ] || continue
    rclone copy "$src/$f" "gdrive:Sinder-Eval/$ts" --quiet || ok=0
  done
  if [ "$ok" = 1 ]; then echo "copied to Google Drive: Sinder-Eval/$ts ($(rclone lsf "gdrive:Sinder-Eval/$ts" | wc -l) files there)"
  else echo "GOOGLE DRIVE COPY FAILED: the files are on the server only ($dst)"; exit 1; fi
else echo "GOOGLE DRIVE NOT CONNECTED: the files are on the server only ($dst)"; exit 1; fi
# old runs on the server: 90 days
find /opt/sinder/eval -mindepth 1 -maxdepth 1 -type d -mtime +90 -exec rm -rf {} +
