#!/usr/bin/env bash
# Runs as root on the server (called by the backup workflow through asroot). Packs a checked Google Sheets export
# (made by tools/backup_sheets.py), encrypts it with the same key and cipher as the database backup, reads the
# encrypted file back to prove it opens, and copies it to Google Drive. Prints no secrets; the key stays where it is.
#   _sheets_backup_root.sh <directory that holds the export> <name of the export folder inside it>
set -euo pipefail
src="$1"; name="$2"; key=/opt/sinder/backup.key; dst=/opt/sinder/backup/sheets
[ -f "$src/$name/manifest.json" ] || { echo "no export at the given path"; exit 1; }
[ -f "$key" ] || { echo "backup key is missing: run the database backup first (it creates the key)"; exit 1; }
umask 077; mkdir -p "$dst"
ts=$(date -u +%Y%m%dT%H%M%SZ); f=$dst/sinder-sheets-$ts.tar.gz.enc
tar -C "$src" -czf - "$name" | openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:"$key" > "$f"
echo "sheets backup written: $(basename "$f") ($(du -h "$f" | cut -f1))"
# read it back: the manifest inside the encrypted file must be the one that was just checked
want=$(sha256sum < "$src/$name/manifest.json" | cut -d' ' -f1)
got=$(openssl enc -d -aes-256-cbc -pbkdf2 -pass file:"$key" < "$f" | tar -xzOf - "$name/manifest.json" | sha256sum | cut -d' ' -f1)
n=$(openssl enc -d -aes-256-cbc -pbkdf2 -pass file:"$key" < "$f" | tar -tzf - | grep -c '\.jsonl$' || true)
[ "$want" = "$got" ] || { echo "READ-BACK FAILED: the encrypted file does not open to the same manifest"; rm -f "$f"; exit 1; }
echo "read back from the encrypted file: manifest matches, $n tab files"
# the row counts of this export are what the next run compares against (half-rows guard); no cell content in it
cp "$src/$name/manifest.json" "$dst/last-manifest.json"
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  if rclone copy "$f" gdrive:Sinder-Backups/sheets --quiet; then echo "copied to Google Drive: Sinder-Backups/sheets ($(rclone lsf gdrive:Sinder-Backups/sheets | wc -l) files there)"; rclone delete gdrive:Sinder-Backups/sheets --min-age 60d --quiet || true
  else echo "GOOGLE DRIVE COPY FAILED"; fi
else echo "Google Drive not connected yet: backup is on the server and as a workflow artifact only"; fi
find "$dst" -name "*.enc" -mtime +14 -delete
echo "sheets backups kept: $(ls -1 "$dst"/*.enc | wc -l)"
