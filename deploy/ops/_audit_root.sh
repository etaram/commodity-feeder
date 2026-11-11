#!/usr/bin/env bash
# Runs as root on the server. Draws a reproducible audit sample from the latest supplier-match evaluation for an
# outside reviewer who labels it blind: sample.csv holds the request and the facts collected about each supplier, in
# random order, with no rank, score or matcher verdict; key.csv (kept in a separate Drive folder until the reviewer is
# done) maps each item back to its request and rank. manifest.json records the seed and the SHA-256 of every file.
# THE LOG IS PUBLIC: counts only.
set -euo pipefail
ts="${1:-$(ls -1 /opt/sinder/eval 2>/dev/null | sort | tail -1)}"; dir="/opt/sinder/eval/$ts"; n="${2:-50}"
case "$ts" in *[!0-9TZ]*|"") echo "no evaluation run found"; exit 1;; esac
[ -f "$dir/rows.jsonl" ] || { echo "rows.jsonl is missing"; exit 1; }
umask 077; out="$dir/audit"; mkdir -p "$out"
python3 - "$dir/rows.jsonl" "$out" "$n" <<'PY'
import csv, hashlib, json, random, sys
rows_path, out, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
seed = 20261111
rows = [json.loads(l) for l in open(rows_path, encoding="utf-8") if l.strip()]
by = {}
for r in rows:
    if int(r.get("rank") or 0) <= 10: by.setdefault((r.get("set"), r.get("query_id")), []).append(r)
rng = random.Random(seed); keys = sorted(by); rng.shuffle(keys)
for k in keys: rng.shuffle(by[k])
picked = []
while len(picked) < n and any(by[k] for k in keys):          # one row per request per round: spread over all requests
    for k in keys:
        if by[k] and len(picked) < n: picked.append(by[k].pop())
rng.shuffle(picked)
with open(f"{out}/sample.csv", "w", newline="", encoding="utf-8") as f, open(f"{out}/key.csv", "w", newline="", encoding="utf-8") as g:
    w = csv.writer(f); k = csv.writer(g)
    w.writerow(["item_id", "request_kind", "request", "supplier", "country", "type", "evidence", "website", "label", "reason"])
    k.writerow(["item_id", "set", "query_id", "rank"])
    for i, r in enumerate(picked, 1):
        iid = f"A{i:02d}"
        w.writerow([iid, "tender title" if str(r.get("query_id", "")).startswith("T") else "product", r.get("query", ""), r.get("supplier", ""), r.get("country", ""),
                    r.get("type", ""), r.get("evidence", ""), r.get("website", ""), "", ""])
        k.writerow([iid, r.get("set", ""), r.get("query_id", ""), r.get("rank", "")])
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
json.dump({"seed": seed, "items": len(picked), "requests_covered": len({(r.get("set"), r.get("query_id")) for r in picked}), "rule": "ranks 1-10 only, one row per request per round, then shuffled",
           "sha256": {"rows.jsonl": sha(rows_path), "sample.csv": sha(f"{out}/sample.csv"), "key.csv": sha(f"{out}/key.csv")}}, open(f"{out}/manifest.json", "w"), indent=1)
m = json.load(open(f"{out}/manifest.json"))
print(f"audit sample: {m['items']} items over {m['requests_covered']} requests; sha256 sample.csv {m['sha256']['sample.csv'][:16]}..., key.csv {m['sha256']['key.csv'][:16]}..., rows.jsonl {m['sha256']['rows.jsonl'][:16]}...")
PY
if command -v rclone >/dev/null 2>&1 && rclone listremotes 2>/dev/null | grep -q "^gdrive:"; then
  rclone copy "$out/sample.csv" "gdrive:Sinder-Eval/$ts/audit" --quiet && rclone copy "$out/manifest.json" "gdrive:Sinder-Eval/$ts/audit" --quiet \
    && rclone copy "$out/key.csv" "gdrive:Sinder-Eval/$ts/audit-key-do-not-open-before-labelling" --quiet \
    && echo "copied to Google Drive: Sinder-Eval/$ts/audit (sample.csv, manifest.json) and the key in its own folder" || echo "the copy to Google Drive failed"
else echo "no Google Drive remote on the server: the files stay in $out"; fi
