#!/bin/sh
# Runs as root on the server (called by checknow-up.sh). Builds and (re)starts only the check-now worker
# (service checknow of the production overlay, leads/check_now.py); the app and the cron service are not touched.
# Prints status lines only: no secrets, no e-mail addresses.
set -eu
. /opt/sinder/server-instance/deploy/ops/_server_compose.sh
[ "$(server_mode)" = production ] || { echo "server mode is $(server_mode): the check-now worker runs in production mode only"; exit 1; }
S=/opt/sinder/checknow
mkdir -p $S && chown 10001 $S && chmod 700 $S
echo "== private supplier list for website look-ups (newest universe.csv left by a runner job, copied on this server only)"
U=$(ls -1t /home/runner/r*/_work/commodity-feeder/commodity-feeder/data/private/universe.csv 2>/dev/null | head -1 || true)
if [ -n "$U" ] && [ ! "$S/universe.csv" -nt "$U" ]; then cp "$U" $S/universe.csv.tmp && chown 10001 $S/universe.csv.tmp && chmod 600 $S/universe.csv.tmp && mv $S/universe.csv.tmp $S/universe.csv
  echo "universe.csv copied ($(wc -l < $S/universe.csv) lines, from $(date -u -r "$U" +%FT%TZ))"
elif [ -f $S/universe.csv ]; then echo "universe.csv kept ($(wc -l < $S/universe.csv) lines, $(date -u -r $S/universe.csv +%FT%TZ))"
else echo "no universe.csv on the server: the website comes from the request, else it is discovered by name"; fi
echo "== build and start"
t0=$(date +%s)
nice -n 15 sh -c ". /opt/sinder/server-instance/deploy/ops/_server_compose.sh; server_compose build checknow" 2>&1 | grep -E "ERROR|error:|Built|naming to" | tail -3 || true
server_compose up -d --no-deps --force-recreate checknow 2>&1 | tail -2
echo "took $(( $(date +%s) - t0 ))s"
sleep 20
printf "%-30s %s\n" "container sinder-server-checknow" "$(docker inspect -f '{{.State.Status}} (restarts {{.RestartCount}})' sinder-server-checknow 2>/dev/null || echo missing)"
echo "== worker log (last lines, e-mails masked)"
docker logs --tail 15 sinder-server-checknow 2>&1 | sed -E 's/[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/<email>/g' | cut -c1-200
