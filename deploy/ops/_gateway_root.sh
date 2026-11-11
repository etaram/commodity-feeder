#!/usr/bin/env bash
# Runs as root on the server. Publishes the private data files over HTTPS under a secret path, so the web app can read
# them without the public repository. Everything outside that path answers 404. The token is never printed.
set -euo pipefail
HOST="${GATEWAY_HOST:-216-158-234-218.sslip.io}"
mkdir -p /opt/sinder/gateway && cd /opt/sinder/gateway
[ -f /opt/sinder/data_token ] || { umask 077; openssl rand -hex 32 > /opt/sinder/data_token; echo "new data token created"; }
T=$(cat /opt/sinder/data_token)
cat > Caddyfile <<CADDY
$HOST {
	@data path /$T/*
	handle @data {
		uri strip_prefix /$T
		reverse_proxy data:8080
	}
	handle {
		respond 404
	}
	log {
		output discard
	}
}
CADDY
chmod 600 Caddyfile
docker rm -f sinder-gateway >/dev/null 2>&1 || true
docker run -d --name sinder-gateway --restart unless-stopped -p 80:80 -p 443:443 --network sinder_default \
  -v /opt/sinder/gateway/Caddyfile:/etc/caddy/Caddyfile:ro -v sinder_gateway:/data caddy:2-alpine >/dev/null
echo "gateway started for $HOST; waiting for the certificate"
for i in $(seq 1 12); do
  c=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$HOST/$T/deploy/README.md" || true)
  [ "$c" = "200" ] && break; sleep 10
done
echo "with the secret path: HTTP $c"
echo "without it:           HTTP $(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$HOST/deploy/README.md" || true)"
echo "wrong path:           HTTP $(curl -s -o /dev/null -w "%{http_code}" --max-time 10 "https://$HOST/0000/deploy/README.md" || true)"
echo "encrypted index:      HTTP $(curl -s -o /dev/null -w "%{http_code} %{size_download} bytes" --max-time 20 "https://$HOST/$T/data/web/winners.enc" || true)"
