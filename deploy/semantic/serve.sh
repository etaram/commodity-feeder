#!/usr/bin/env bash
# Semantic supplier search service, for the app's data gateway to call later. NOT started by any workflow and NOT
# wired into the app. Run as root on the server once the embedding job has finished:
#   bash deploy/semantic/serve.sh            start (or restart)
#   bash deploy/semantic/serve.sh stop       stop and remove
# The container joins the private docker network of the stack (sinder_default) and publishes no port, so only the
# other containers reach it: GET http://semantic-search:8099/search?q=<text>&n=<count>  ->  {"results": [{"i", "key",
# "score"}]}, where i is the row of the supplier index (data/web/suppliers.enc) and key the app's dedupeKey
# (lib/supmatch.ts). GET /health gives the vector count. It logs no request text.
# Low priority and limited like the other model jobs: 1 CPU and 2 GB is enough for one query at a time.
set -euo pipefail
S=/opt/sinder/semantic
docker rm -f semantic-search >/dev/null 2>&1 || true
[ "${1:-}" = stop ] && { echo "stopped"; exit 0; }
[ -f "$S/vectors/LATEST" ] || { echo "no finished vector file yet (see deploy/ops/semantic-status.sh)"; exit 1; }
[ -f "$S/semantic_rank.py" ] || { echo "the embedding job has not run on this server"; exit 1; }
docker run -d --name semantic-search --restart unless-stopped --network sinder_default --cpus 1 --cpu-shares 256 --memory 2g \
  -e SEM_THREADS=1 -e HF_HUB_DISABLE_TELEMETRY=1 -v "$S":/s python:3.12-slim \
  nice -n 10 /s/venv/bin/python /s/semantic_rank.py serve --out /s/vectors --cache /s/models --port 8099 >/dev/null
echo "semantic-search started on the private docker network (no published port)"
