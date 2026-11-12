#!/usr/bin/env bash
# Runs as root on the server (called by deploy/ops/serverpanel-install.sh with the workflow's checkout as $1).
# Installs the collector and its timer, lets the data service serve /_server/ from a read-only host folder, and checks
# the result from inside the docker network. Prints sizes, key names and states only: never a value of a secret.
set -euo pipefail
W="$1"; B=/opt/sinder/serverpanel; OUT=$B/public; ST=/var/lib/sinder-serverpanel
PY=$(command -v python3) || { echo "python3 is missing on the server"; exit 1; }

echo "== collector"
install -d -m 755 "$B" "$OUT"
install -d -m 700 "$ST"
install -m 755 "$W/deploy/ops/serverpanel/collect.py" "$B/collect.py"
unit() { printf '%s\n' "$2" > "/etc/systemd/system/$1"; }
unit sinder-serverpanel.service "[Unit]
Description=Sinder: server status for the admin panel (deploy/ops/serverpanel)
[Service]
Type=oneshot
ExecStart=$PY $B/collect.py
Nice=19
IOSchedulingClass=idle
CPUWeight=10
IOWeight=10
MemoryMax=256M
TimeoutStartSec=90"
unit sinder-serverpanel.timer "[Unit]
Description=Sinder: server status every 2 minutes
[Timer]
OnCalendar=*:0/2:40
AccuracySec=10s
[Install]
WantedBy=timers.target"
systemctl daemon-reload
systemctl enable --now sinder-serverpanel.timer >/dev/null 2>&1
systemctl start sinder-serverpanel.service
echo "timer: $(systemctl is-enabled sinder-serverpanel.timer) / $(systemctl is-active sinder-serverpanel.timer); last run: $(systemctl show -p Result --value sinder-serverpanel.service)"
ls -l "$OUT" | awk 'NR>1{print "  " $1, $5, $9}'

echo "== data service"
D=/opt/sinder/repo/deploy; CURL=curlimages/curl:8.10.1
# HTTP status of a path, asked from a container on the app's docker network
code() { docker run --rm --network sinder_default "$CURL" -s -o /dev/null -w '%{http_code}' --max-time 15 "http://$1:8080/$2" || true; }
if grep -q '/_server/' "$D/docker-compose.yml"; then
  CF="$D/docker-compose.yml"; echo "compose on main already serves /_server/"
else
  # the change is not on main yet: apply this branch's compose file to the data service only, from the deploy folder
  # (so .env and relative paths resolve as usual); the copy is removed right after
  CF="$D/.serverpanel-compose.yml"; cp "$W/deploy/docker-compose.yml" "$CF"; trap 'rm -f "$D/.serverpanel-compose.yml"; docker rm -f sinder-data-candidate >/dev/null 2>&1 || true' EXIT
  echo "compose from this branch (main does not serve /_server/ yet)"
fi
# try the new configuration in a separate container first; the running data service is replaced only if it works
SCRIPT=$(cd "$D" && docker compose -f "$CF" config --format json 2>/dev/null | "$PY" -c 'import json,sys; print(json.load(sys.stdin)["services"]["data"]["command"][0])')
[ -n "$SCRIPT" ] || { echo "could not read the data service command from the compose file"; exit 1; }
VOL=$(docker volume ls -q | grep -E '^(sinder|deploy)_repo$' | head -1); [ -n "$VOL" ] || { echo "repository volume not found"; exit 1; }
docker rm -f sinder-data-candidate >/dev/null 2>&1 || true
docker run -d --name sinder-data-candidate --network sinder_default -v "$VOL":/srv/repo:ro -v "$OUT":/srv/server:ro \
  --entrypoint /bin/sh caddy:2-alpine -c "$SCRIPT" >/dev/null
sleep 3
c1=$(code sinder-data-candidate deploy/README.md); c2=$(code sinder-data-candidate _server/status.json)
docker rm -f sinder-data-candidate >/dev/null 2>&1 || true
echo "trial container: repository file $c1, /_server/status.json $c2"
[ "$c1" = "200" ] && [ "$c2" = "200" ] || { echo "trial failed: data service left as it is"; exit 1; }
before=$(code data deploy/README.md)
(cd "$D" && docker compose -f "$CF" up -d --no-deps data 2>&1 | tail -3)
sleep 4
after=$(code data deploy/README.md)
echo "data service: repository file before $before, after $after; /_server/status.json $(code data _server/status.json)"
if [ "$after" != "200" ]; then
  echo "the data service no longer serves the repository: rolling back to the compose file on main"
  (cd "$D" && docker compose up -d --no-deps --force-recreate data 2>&1 | tail -3)
  sleep 4; echo "after rollback: $(code data deploy/README.md)"; exit 1
fi

echo "== what the app reads (from inside the docker network)"
for f in status.json history.json; do
  docker run --rm --network sinder_default "$CURL" -s --max-time 15 "http://data:8080/_server/$f" | "$PY" -c '
import json, sys
raw = sys.stdin.buffer.read(); d = json.loads(raw)
print(sys.argv[1], len(raw), "bytes, keys:", ",".join(d.keys()))
if "host" in d: print("  host keys:", ",".join(d["host"].keys()))
if "points" in d: print("  points:", len(d["points"]), "cols:", ",".join(d["cols"]))
if "containers" in d: print("  containers:", len(d["containers"] or []), "runners:", len(d["runners"] or []), "models running:", len(d["models"] or []), "journal lines:", len(d["journal"] or []) if d.get("journal") is not None else "no journal")
' "$f"
done
echo "folder listing at /_server/ (expect 404, no browsing): $(code data _server/)"
# the same path through the data gateway the web app uses in production; the secret path is never printed
if [ -s /opt/sinder/data_token ] && [ -f /opt/sinder/gateway/Caddyfile ]; then
  H=$(awk 'NF{print $1; exit}' /opt/sinder/gateway/Caddyfile); T=$(cat /opt/sinder/data_token)
  echo "through the data gateway: $(curl -s -o /dev/null -w '%{http_code} %{size_download} bytes' --max-time 20 "https://$H/$T/_server/status.json" || echo failed)"
  echo "gateway without the secret path: $(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "https://$H/_server/status.json" || echo failed)"
fi
