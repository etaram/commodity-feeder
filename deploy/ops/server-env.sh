#!/usr/bin/env bash
# Owner's one step: copies the values he added as repository secrets named SERVER_<KEY> into the server's .env.
# Only the keys below, only secrets that are not empty. The values go to the server over stdin (never as arguments,
# never printed); the old .env is kept as .env.bak-<time> (mode 600). Prints key NAMES only. Then restarts the
# server instance so it reads them. After this, the SERVER_* secrets can be deleted from GitHub.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
KEYS="AUTH_SECRET TEAM_USER TEAM_PASSCODE GOOGLE_SERVICE_ACCOUNT_JSON WEB_INDEX_KEY ANTHROPIC_API_KEY ANTHROPIC_WORKSPACE_ID"
umask 077; f=$(mktemp)
for k in $KEYS; do n="SERVER_$k"; v="${!n:-}"; if [ -n "$v" ]; then printf '%s=%s\n' "$k" "$(printf '%s' "$v" | tr -d '\r\n')" >> "$f"; fi; done
echo "secrets provided: $(cut -d= -f1 "$f" | tr '\n' ' ')"
[ -s "$f" ] || { rm -f "$f"; echo "no SERVER_* secret found: nothing changed"; exit 0; }
instance_run ""   # brings the server-instance checkout up to date (no script run)
docker run --rm -i --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- sh /opt/sinder/server-instance/deploy/ops/_server_env_root.sh < "$f"
rm -f "$f"
