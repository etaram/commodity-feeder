#!/usr/bin/env bash
# Owner's one step: copies the values he added as repository secrets named SERVER_<KEY> into the server's .env.
# Only the keys below, only secrets that are not empty. The values go to the server over stdin (never as arguments,
# never printed); the old .env is kept as .env.bak-<time> (mode 600). Prints key NAMES only. Then restarts the
# server instance so it reads them. After this, the SERVER_* secrets can be deleted from GitHub.
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
# the first line: the test instance; the rest: what production mode needs (deploy/CUTOVER.md, cutover-prepare lists them)
KEYS="AUTH_SECRET TEAM_USER TEAM_PASSCODE GOOGLE_SERVICE_ACCOUNT_JSON WEB_INDEX_KEY ANTHROPIC_API_KEY ANTHROPIC_WORKSPACE_ID
  ZOHO_SMTP_USER ZOHO_SMTP_PASS SEND_APPROVERS NOTIFY_EMAIL RESEND_API_KEY TELEGRAM_BOT_TOKEN TELEGRAM_WEBHOOK_SECRET
  VAPID_PRIVATE_KEY VAPID_SUBJECT"
umask 077; f=$(mktemp)
# WEB_INDEX_KEY is not a repository secret: it lives in the Supplier Universe sheet, tab Config (where every data job
# reads it). When no SERVER_WEB_INDEX_KEY is given, read it from there with the service account, in a throwaway
# container, never printed.
if [ -z "${SERVER_WEB_INDEX_KEY:-}" ] && [ -n "${SERVER_GOOGLE_SERVICE_ACCOUNT_JSON:-}" ]; then
  SERVER_WEB_INDEX_KEY=$(GOOGLE_SERVICE_ACCOUNT_JSON="$SERVER_GOOGLE_SERVICE_ACCOUNT_JSON" docker run --rm -e GOOGLE_SERVICE_ACCOUNT_JSON \
    -v "$(cd "$(dirname "$0")/../.." && pwd)":/w:ro -w /w python:3.12-slim sh -c \
    'pip -q install --disable-pip-version-check requests google-auth >/dev/null 2>&1; python -I -c "import sys; sys.path.insert(0,\"/w\"); from leads.push import UNIVERSE_SHEET, Sheets; print(next((r[1] for r in Sheets().values(UNIVERSE_SHEET, \"Config!A1:B10\") if len(r) > 1 and r[0] == \"WEB_INDEX_KEY\"), \"\"))"' 2>/dev/null || true)
  [ -n "$SERVER_WEB_INDEX_KEY" ] && echo "WEB_INDEX_KEY read from the Config tab" || echo "WEB_INDEX_KEY: not found in the Config tab"
fi
for k in $KEYS; do n="SERVER_$k"; v="${!n:-}"; if [ -n "$v" ]; then printf '%s=%s\n' "$k" "$(printf '%s' "$v" | tr -d '\r\n')" >> "$f"; fi; done
echo "secrets provided: $(cut -d= -f1 "$f" | tr '\n' ' ')"
[ -s "$f" ] || { rm -f "$f"; echo "no SERVER_* secret found: nothing changed"; exit 0; }
instance_run ""   # brings the server-instance checkout up to date (no script run)
docker run --rm -i --privileged --pid=host alpine:3.20 nsenter -t 1 -m -u -n -i -- sh /opt/sinder/server-instance/deploy/ops/_server_env_root.sh < "$f"
rm -f "$f"
