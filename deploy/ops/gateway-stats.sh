#!/usr/bin/env bash
# How many requests the private data gateway served in the last 15 minutes, by status. Paths are never logged.
docker logs --since 15m sinder-gateway 2>&1 | grep -o '"status":[0-9]*' | sort | uniq -c || true
echo "total lines: $(docker logs --since 15m sinder-gateway 2>&1 | grep -c '"status"')"
docker logs --since 15m sinder-gateway 2>&1 | grep '"status":200' | grep -o '"remote_ip":"[^"]*"' | sort | uniq -c | sort -rn | head -5
