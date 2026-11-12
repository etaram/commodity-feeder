#!/usr/bin/env bash
# Runs as root on the server (called by deploy/ops/enrich-*.sh through asroot). Supplier enrichment job
# (leads/enrich_server.py): each supplier's own public website (robots.txt respected, polite) plus free public sources
# (Google News RSS, Wikidata, public search snippets when switched on), in a low-priority, capped, resumable container.
#   probe  <checkout>        what the job can use here (counts and versions only)
#   sample <checkout>        measurement run: 200 producers + 100 traders, all lanes, in the background (container "enrich")
#   start  <checkout>        the full run in priority order (container "enrich", restarts with the server, resumes)
#   status <checkout>        progress counts, lane counts, fill rates; sample metrics when a sample ran
#   stop   <checkout>        stops the container (the files stay; start resumes where it stopped)
#   review <checkout>        the 30-record hand-check file, ENCRYPTED to the reviewer's public key (deploy/enrich/review_pub.pem)
#   people <checkout>        the registry people lane's measurement sample (leads/people_registry.py), in its own folder
#                            and container ("enrich-people"); the full run is not touched. First call starts it; a call
#                            while it runs prints counts; a call after it finished prints the metrics and the sealed
#                            review file. A new commit starts a new sample.
# Companies House: the key is used only when the repository secret COMPANIES_HOUSE_API_KEY exists (written by
# deploy/ops/enrich-start.sh and enrich-people.sh to $E/.ch.env, root only); without it the UK register stays off.
# Limits: 1.5 CPUs, 3 GB, CPU shares 128, nice 19, idle I/O: the database, the data gateway, the website, the collectors,
# backups and the semantic job keep priority. Folder /opt/sinder/enrich (root only): code copy, venv, queue, lane files,
# status.json (counts only, readable by the server panel collector), export/enrich.jsonl.gz (for the company-check workflow).
# THE LOG IS PUBLIC: counts, timings and versions only. No supplier name, contact or URL is printed.
set -euo pipefail
mode="$1"; repo="$2"
E=/opt/sinder/enrich
IMG=python:3.12-slim
LIMITS=(--cpus 1.5 --cpu-shares 128 --memory 3g --memory-swap 3g)
umask 077; mkdir -p "$E"; chmod 711 "$E"

seal() {   # $1 a file: printed only as ciphertext (hybrid encryption to the reviewer's public key; the private key is not
           # on this server), in lines of 40,000 characters (GitHub drops longer log lines); join the REVIEW-DATA lines
  local k; k=$(mktemp)
  openssl rand -hex 32 > "$k"
  gzip -c "$1" | openssl enc -aes-256-cbc -pbkdf2 -salt -pass file:"$k" -out "$k.enc"
  openssl pkeyutl -encrypt -pubin -inkey "$repo/deploy/enrich/review_pub.pem" -pkeyopt rsa_padding_mode:oaep -in "$k" -out "$k.key"
  echo "REVIEW-KEY $(base64 -w0 "$k.key")"
  base64 -w0 "$k.enc" | fold -w 40000 | sed 's/^/REVIEW-DATA /'; echo
  rm -f "$k" "$k".*
}
code() {   # a copy of the code the job runs, so the runner's workspace can change under it
  rm -rf "$E/code.new"; mkdir -p "$E/code.new/dealdesk/lib"
  cp -r "$repo/leads" "$E/code.new/leads"; cp "$repo/dealdesk/lib/countrynames.json" "$E/code.new/dealdesk/lib/"
  rm -rf "$E/code"; mv "$E/code.new" "$E/code"; chmod -R go-rwx "$E/code"
  echo "code copied: $(git -c safe.directory='*' -C "$repo" rev-parse --short HEAD 2>/dev/null)"
}
venv() {
  if [ -d "$E/venv" ] && docker run --rm "${LIMITS[@]}" -v "$E":/e "$IMG" /e/venv/bin/python -c "import requests, cryptography, phonenumbers, pycountry, pypinyin, cv2" >/dev/null 2>&1; then return 0; fi
  echo "installing requests, cryptography, phonenumbers, pycountry, pypinyin, opencv-python-headless into $E/venv"
  rm -rf "$E/venv"
  docker run --rm "${LIMITS[@]}" -v "$E":/e "$IMG" sh -c 'python -m venv /e/venv && /e/venv/bin/pip install -q --disable-pip-version-check requests cryptography phonenumbers pycountry pypinyin opencv-python-headless 2>&1 | grep -iE "^error" | head -3; /e/venv/bin/python -c "import cv2, requests; print(\"opencv\", cv2.__version__, \"requests\", requests.__version__)"'
}
queue() {   # the supplier index the app reads, decrypted inside the container only; the queue file stays root-only
  local key_env="$E/.key.env" V=/var/lib/docker/volumes/sinder_repo/_data/data/web
  grep -E '^WEB_INDEX_KEY=.+' /opt/sinder/repo/deploy/.env > "$key_env" || { rm -f "$key_env"; echo "WEB_INDEX_KEY missing"; return 1; }
  chmod 600 "$key_env"
  docker run --rm "${LIMITS[@]}" --env-file "$key_env" -v "$E":/e -v "$V":/web:ro -w /e/code "$IMG" ionice -c 3 nice -n 19 /e/venv/bin/python -m leads.enrich_server queue --index /web/suppliers.enc --dir /e || { rm -f "$key_env"; return 1; }
  rm -f "$key_env"
}
envf() { [ -s "$E/.ch.env" ] && echo "--env-file $E/.ch.env"; }
launch() {   # $1 restart policy, rest: arguments of leads.enrich_server run
  local pol="$1"; shift
  docker rm -f enrich >/dev/null 2>&1 || true
  # shellcheck disable=SC2046
  docker run -d --name enrich --restart "$pol" "${LIMITS[@]}" $(envf) -e PYTHONUNBUFFERED=1 -v "$E":/e -w /e/code "$IMG" \
    ionice -c 3 nice -n 19 /e/venv/bin/python -m leads.enrich_server run --dir /e "$@" >/dev/null
  sleep 20; docker ps --filter name=^enrich$ --format 'container {{.Names}}: {{.Status}}'
}

if [ "$mode" = sample ]; then
  code; venv
  [ -s "$E/queue.jsonl" ] || queue
  docker run --rm "${LIMITS[@]}" -v "$E":/e -w /e/code "$IMG" /e/venv/bin/python -m leads.enrich_server sample --dir /e --manufacturers 200 --traders 100
  # a new sample measures the current code: earlier lane files move aside (only before the full run has started)
  if [ -s "$E/site.jsonl" ] && [ ! -f "$E/full-run-started" ]; then
    docker rm -f enrich >/dev/null 2>&1 || true
    n=1; while [ -d "$E/sample-$n" ]; do n=$((n+1)); done; mkdir -p "$E/sample-$n"
    for f in site press people registry wikidata; do [ -f "$E/$f.jsonl" ] && mv "$E/$f.jsonl" "$E/sample-$n/"; done
    rm -f "$E/status.json" "$E/review.jsonl"; echo "earlier sample files moved to sample-$n"
  fi
  # the search-snippet lane (people) answered the first query with a block page on 12 Nov 2026: left out of the sample
  launch no --only sample --lanes site,press,wikidata --workers 16 --minutes 100
  exit 0
fi
if [ "$mode" = start ]; then
  code; venv
  [ -s "$E/queue.jsonl" ] || queue
  if [ ! -f "$E/full-run-started" ] && [ -s "$E/site.jsonl" ]; then   # the last sample's files move aside: the full run starts clean
    docker rm -f enrich >/dev/null 2>&1 || true
    n=1; while [ -d "$E/sample-$n" ]; do n=$((n+1)); done; mkdir -p "$E/sample-$n"
    for f in site press people registry wikidata; do [ -f "$E/$f.jsonl" ] && mv "$E/$f.jsonl" "$E/sample-$n/"; done
    rm -f "$E/status.json"; echo "sample files moved to sample-$n"
  fi
  touch "$E/full-run-started"
  lanes=$(cat "$E/lanes" 2>/dev/null || echo site,press,registry,wikidata)
  # a lanes file written before the registry lane existed (12 Nov 2026) gains it; "people" (search snippets) is gone
  case ",$lanes," in *,registry,*) ;; *) lanes="$lanes,registry" ;; esac
  lanes=$(echo "$lanes" | tr ',' '\n' | grep -vx people | paste -sd, -)
  [ -s "$E/.ch.env" ] && echo "Companies House: key present (UK register on)" || echo "Companies House: no key (UK register off)"
  echo "lanes: $lanes"
  # 24 workers: the sample used about 0.5 of its 1.5 CPUs with 16 (the work is waiting on remote sites)
  launch unless-stopped --lanes "$lanes" --workers 24
  exit 0
fi
if [ "$mode" = people ]; then
  P="$E/psample"; sha=$(git -c safe.directory='*' -C "$repo" rev-parse HEAD 2>/dev/null | cut -c1-12 || echo none)
  if docker ps --filter name=^enrich-people$ --format '{{.Names}}' | grep -q . && [ "$(cat "$P/sha" 2>/dev/null)" = "$sha" ]; then
    echo "people sample running ($(cat "$P/sha" 2>/dev/null))"
    python3 -c "import json; s=json.load(open('$P/status.json')); print(json.dumps({'registry_people': s.get('registry_people'), 'blocked': s.get('blocked')}))" 2>/dev/null || echo "no counts yet"
    docker logs --tail 8 enrich-people 2>&1 | grep -vE "https?://|@" | cut -c1-160 || true
    exit 0
  fi
  echo "previous sample container: $(docker ps -a --filter name=^enrich-people$ --format '{{.Status}}') code $(cat "$P/sha" 2>/dev/null), now $sha"
  docker logs --tail 12 enrich-people 2>&1 | grep -vE "https?://|@" | cut -c1-200 || true
  if [ -s "$P/registry.jsonl" ] && [ "$(cat "$P/sha" 2>/dev/null)" = "$sha" ]; then
    echo "== people sample metrics (counts only), code $sha"
    docker run --rm "${LIMITS[@]}" -v "$E":/e -w /e/pcode "$IMG" /e/venv/bin/python -m leads.enrich_server people-metrics --dir /e/psample
    echo "== hand-check file (sealed)"; seal "$P/people_review.jsonl"
    exit 0
  fi
  venv
  # its own code copy: the full run's copy (code/) is not replaced under it
  rm -rf "$E/pcode"; mkdir -p "$E/pcode/dealdesk/lib"; cp -r "$repo/leads" "$E/pcode/leads"; cp "$repo/dealdesk/lib/countrynames.json" "$E/pcode/dealdesk/lib/"; chmod -R go-rwx "$E/pcode"
  rm -rf "$P"; mkdir -p "$P"; echo "$sha" > "$P/sha"
  docker run --rm "${LIMITS[@]}" -v "$E":/e -w /e/pcode "$IMG" /e/venv/bin/python -m leads.enrich_server people-sample --dir /e --out /e/psample --per 40
  docker rm -f enrich-people >/dev/null 2>&1 || true
  # shellcheck disable=SC2046
  docker run -d --name enrich-people --restart no --cpus 0.5 --memory 1g $(envf) -e PYTHONUNBUFFERED=1 -v "$E":/e -w /e/pcode "$IMG" \
    ionice -c 3 nice -n 19 /e/venv/bin/python -m leads.enrich_server run --dir /e/psample --lanes registry --workers 0 --minutes 40 >/dev/null
  sleep 15; docker ps -a --filter name=^enrich-people$ --format 'container {{.Names}}: {{.Status}}'
  exit 0
fi
if [ "$mode" = stop ]; then
  docker stop -t 30 enrich >/dev/null 2>&1 && echo "stopped" || echo "not running"
  docker rm enrich >/dev/null 2>&1 || true
  exit 0
fi
if [ "$mode" = status ]; then
  docker ps -a --filter name=^enrich$ --format 'container {{.Names}}: {{.Status}}'
  docker stats --no-stream --format '{{.Name}} cpu {{.CPUPerc}} mem {{.MemUsage}}' enrich 2>/dev/null || true
  [ -f "$E/status.json" ] && python3 -m json.tool "$E/status.json" || echo "no status yet"
  ls -la "$E" | awk 'NR>1 && $9 ~ /jsonl|keys|status/ {print $5, $9}'
  docker logs --tail 15 enrich 2>&1 | grep -vE "https?://|@" | cut -c1-160 || true
  if [ -s "$E/sample.keys" ] && [ -d "$E/venv" ]; then
    echo "== sample metrics (counts and rates only)"
    docker run --rm "${LIMITS[@]}" -v "$E":/e -w /e/code "$IMG" /e/venv/bin/python -m leads.enrich_server metrics --dir /e --keys sample.keys
  fi
  exit 0
fi
if [ "$mode" = review ]; then
  [ -s "$E/review.jsonl" ] || { echo "no review file (run status after a sample)"; exit 1; }
  seal "$E/review.jsonl"
  exit 0
fi
if [ "$mode" = probe ]; then
  set +e +o pipefail
  echo "== ollama models"; ls /var/lib/docker/volumes/ollama/_data/models/manifests/registry.ollama.ai/library/qwen3 2>/dev/null | tr '\n' ' '; echo
  echo "== semantic job"; docker stats --no-stream --format '{{.Name}} {{.CPUPerc}} {{.MemUsage}}' | head
  V=/var/lib/docker/volumes/sinder_repo/_data
  echo "== index"; ls -la $V/data/web/suppliers.enc 2>/dev/null | awk '{print $5, $6, $7, $8}'
  echo "== private data on volume"; ls $V/data/private 2>/dev/null | head; ls $V/data/checks 2>/dev/null | head
  echo "== zbar/opencv on host"; command -v zbarimg || echo "no zbarimg"; python3 -c "import cv2" 2>/dev/null && echo "cv2 on host" || echo "no cv2 on host"
  if [ -s "$E/queue.jsonl" ] && [ -d "$E/venv" ]; then
    echo "== queue by country: [country, records, with website, producers] (counts only)"
    # the runner's checkout, read-only (the running job's code copy is not touched)
    docker run --rm "${LIMITS[@]}" -v "$E":/e -v "$repo":/r:ro -w /r "$IMG" /e/venv/bin/python -m leads.enrich_server countries --dir /e
  fi
  if [ -d "$E/venv" ]; then
    echo "== official registers for the people lane: HTTP status and size only; the raw answers are sealed to the reviewer key"
    docker run --rm "${LIMITS[@]}" -v "$E":/e -v "$repo":/r:ro -w /r "$IMG" /e/venv/bin/python -m leads.people_registry probe /e/people_probe.json
    for u in https://recherche-entreprises.api.gouv.fr/search?q=542051180 https://api.insee.fr/; do   # connection detail only
      docker run --rm curlimages/curl:8.10.1 -sS -o /dev/null -w "%{http_code} %{remote_ip} " --max-time 20 -A "Mozilla/5.0 (compatible; SinderCompanyCheck/1.0)" "$u" 2>&1 | cut -c1-160; echo " ${u%%\?*}"
      docker run --rm curlimages/curl:8.10.1 -4 -sS -o /dev/null -w "ipv4 %{http_code} " --max-time 20 "$u" 2>&1 | cut -c1-160; echo
    done
    getent ahosts recherche-entreprises.api.gouv.fr | head -3
    seal "$E/people_probe.json"; rm -f "$E/people_probe.json"
  fi
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
