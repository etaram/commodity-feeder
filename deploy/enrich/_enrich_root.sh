#!/usr/bin/env bash
# Runs as root on the server (called by deploy/ops/enrich-*.sh through asroot). Supplier enrichment job: reads each
# supplier's own public website (robots.txt respected, polite), plus free public sources (Google News RSS, Wikidata,
# GLEIF), in a low-priority, capped, resumable container. See leads/enrich_server.py.
#   probe  <checkout>   what the job can use here (counts and versions only)
# THE LOG IS PUBLIC: counts, timings and versions only. No supplier name, contact or URL is printed.
set -euo pipefail
mode="$1"; repo="$2"
E=/opt/sinder/enrich
IMG=python:3.12-slim
umask 077; mkdir -p "$E"; chmod 700 "$E"

if [ "$mode" = probe ]; then
  set +e +o pipefail
  echo "== ollama models"; ls /var/lib/docker/volumes/ollama/_data/models/manifests/registry.ollama.ai/library/qwen3 2>/dev/null | tr '\n' ' '; echo
  echo "== semantic job"; docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' | head
  V=/var/lib/docker/volumes/sinder_repo/_data
  echo "== index"; ls -la $V/data/web/suppliers.enc 2>/dev/null | awk '{print $5, $6, $7, $8}'
  echo "== private data on volume"; ls $V/data/private 2>/dev/null | head; ls $V/data/checks 2>/dev/null | head
  echo "== zbar/opencv on host"; command -v zbarimg || echo "no zbarimg"; python3 -c "import cv2" 2>/dev/null && echo "cv2 on host" || echo "no cv2 on host"
  echo "== egress from a container"
  for u in https://news.google.com/rss/search?q=test https://html.duckduckgo.com/html/?q=test https://www.wikidata.org/w/api.php https://api.gleif.org/api/v1/lei-records?page%5Bsize%5D=1 https://pypi.org/simple/opencv-python-headless/; do
    docker run --rm curlimages/curl:8.10.1 -s -o /dev/null -w "%{http_code} " --max-time 15 -A "Mozilla/5.0 (compatible; SinderCompanyCheck/1.0)" "$u" || true; echo " ${u%%\?*}"
  done
  # field shape of the supplier index (value counts of the role fields only)
  key_env="$E/.key.env"; grep -E '^WEB_INDEX_KEY=.+' /opt/sinder/repo/deploy/.env > "$key_env"; chmod 600 "$key_env"
  docker run --rm --cpus 1 --memory 3g --env-file "$key_env" -v $V/data/web:/web:ro "$IMG" sh -c 'pip install -q --disable-pip-version-check cryptography 2>/dev/null >/dev/null; python - <<"PY"
import base64, gzip, json, os
from collections import Counter
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
b = open("/web/suppliers.enc", "rb").read()
rows = json.loads(gzip.decompress(AESGCM(base64.b64decode(os.environ["WEB_INDEX_KEY"])).decrypt(b[:12], b[12:], None)))
print("records", len(rows))
keys = Counter(k for r in rows for k in r)
print("fields", dict(keys.most_common()))
for f in ("ty", "td", "epc", "tr", "lg", "em", "x"):
    print(f, Counter(str(r.get(f, ""))[:30] for r in rows).most_common(12))
print("with website", sum(1 for r in rows if r.get("web")))
print("with website by ty", Counter(r.get("ty", "") for r in rows if r.get("web")).most_common(10))
PY'
  rm -f "$key_env"
  exit 0
fi
echo "unknown mode"; exit 1
