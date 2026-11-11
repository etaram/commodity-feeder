#!/usr/bin/env bash
# Runs as root on the server (called by the restore-drill workflow through asroot). Two steps around the restore drill:
#   _restore_root.sh open <work directory> <uid of the runner user>
#       decrypts the newest /opt/sinder/backup/sheets/*.enc with /opt/sinder/backup.key and unpacks it as
#       <work directory>/export, readable by the runner user only. The key is read by openssl from its file: it is
#       never copied, printed or passed on a command line.
#   _restore_root.sh clean <work directory>
#       removes the work directory with the plain export in it. Run in an always() step.
# THE LOG IS PUBLIC: this script prints file names, sizes and counts only.
set -euo pipefail
mode="$1"; work="$2"; key=/opt/sinder/backup.key; src=/opt/sinder/backup/sheets
# the only directory this script will fill or remove: restore-drill-<run id> made by the workflow
case "$(basename "$work")" in restore-drill-*[!0-9]*|restore-drill-) echo "bad work directory"; exit 1;; restore-drill-*) ;; *) echo "bad work directory"; exit 1;; esac
case "$work" in /*) ;; *) echo "bad work directory"; exit 1;; esac

if [ "$mode" = clean ]; then
  rm -rf -- "$work"
  echo "work directory removed: no plain export is left on the runner"
  exit 0
fi

[ "$mode" = open ] || { echo "unknown mode"; exit 1; }
uid="$3"
case "$uid" in *[!0-9]*|"") echo "bad uid"; exit 1;; esac
[ -d "$work" ] || { echo "work directory is missing"; exit 1; }
[ -f "$key" ] || { echo "backup key is missing on the server"; exit 1; }
f=$(ls -1t "$src"/sinder-sheets-*.tar.gz.enc 2>/dev/null | head -1 || true)
[ -n "$f" ] || { echo "no Sheets backup on the server: run the backup workflow first"; exit 1; }
umask 077
dec() { openssl enc -d -aes-256-cbc -pbkdf2 -pass file:"$key" < "$f"; }
# look before unpacking: one top folder, no path that climbs out of it
list=$(dec | tar -tzf -) || { echo "the newest backup does not open with the key"; exit 1; }
top=$(printf '%s\n' "$list" | cut -d/ -f1 | sort -u)
[ "$(printf '%s\n' "$top" | wc -l)" = 1 ] && [ -n "$top" ] || { echo "unexpected layout inside the backup"; exit 1; }
if printf '%s\n' "$list" | grep -Eq '(^/|(^|/)\.\.(/|$))'; then echo "unsafe path inside the backup"; exit 1; fi
tmp="$work/unpack"; mkdir "$tmp"
dec | tar -xzf - -C "$tmp" --no-same-owner --no-same-permissions
[ -f "$tmp/$top/manifest.json" ] || { echo "no manifest inside the backup"; exit 1; }
mv "$tmp/$top" "$work/export"; rmdir "$tmp"
chown -R "$uid" "$work/export"; chmod -R u=rwX,go= "$work/export"
age=$(( ( $(date +%s) - $(stat -c %Y "$f") ) / 3600 ))
echo "opened the newest Sheets backup: $(basename "$f") ($(du -h "$f" | cut -f1), written ${age}h ago), $(ls -1 "$work/export" | grep -c '\.jsonl$' || true) tab files"
