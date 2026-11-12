#!/usr/bin/env bash
# Readiness for moving desk.sinder.pro from Vercel to the server instance (deploy/CUTOVER.md). Safe at any time:
# changes no setting, restarts nothing, touches no webhook, Vercel or DNS (it only brings the server-instance checkout
# up to date). Prints key NAMES and set/missing only, never a value. Ends with the exact list of repository secrets
# the owner still has to add (SERVER_<KEY>, read by the server-env task).
set -euo pipefail
. "$(dirname "$0")/_instance_sync.sh"
OUT=$(instance_run _cutover_prepare_root.sh)
st() { echo "$OUT" | awk -v k="$1" '$1=="K" && $2==k {print $3}'; }
# HAS_<KEY>=true|false: whether a repository secret that server-env maps to <KEY> exists (server-ops.yml passes only
# that boolean to this task, never a value)
has() { local n="HAS_$1"; case "${!n:-}" in true) echo yes;; false) echo no;; *) echo "?";; esac; }
echo "$OUT" | grep -v '^K ' | grep -v '^server-instance at' || true
echo "$OUT" | grep '^server-instance at' || true
echo
echo "== readiness for production mode (server .env, names only)"
printf "%-28s %-9s %-12s %s\n" KEY ".env" "repo secret" "role"
MUST=(); RUN_ENV=0
row() { # key, role, how: secret (owner adds SERVER_<key>) | auto (generated on the server) | default (plain value in the prod overlay) | compose
  local k=$1 role=$2 how=$3 s; s=$(st "$k")
  [ "$k" = TELEGRAM_BOT_TOKEN ] && [ "$(st sinder_desk_bot)" = set ] && s=set
  local h="-"; [ "$how" = secret ] && h=$(has "$k")
  case "$how" in
    auto) [ "$s" = set ] || s="$s (generated)";;
    default) [ "$s" = set ] || s="default";;
    compose) s="compose";;
  esac
  printf "%-28s %-9s %-12s %s\n" "$k" "$s" "$h" "$role"
  if [ "$how" = secret ] && [ "$s" != set ]; then
    if [ "$h" = yes ]; then RUN_ENV=1; else MUST+=("SERVER_$k"); fi
  fi
}
row AUTH_SECRET            "required; server's own value is kept: everyone signs in again, MCP addresses change" auto
row GOOGLE_SERVICE_ACCOUNT_JSON "required (sheets)" secret
row ANTHROPIC_API_KEY      "required (AI)" secret
row WEB_INDEX_KEY          "required (encrypted data index)" secret
row ZOHO_SMTP_USER         "mail: on only if USER+PASS+SEND_APPROVERS set" secret
row ZOHO_SMTP_PASS         "mail (sensitive on Vercel, cannot be read back)" secret
row SEND_APPROVERS         "mail: who may approve sending (F14)" secret
row ZOHO_SMTP_HOST         "mail (smtp.zoho.com)" default
row ZOHO_FROM_ADDRESS      "mail (desk@sinder.pro)" default
row MAIL_ABOUT             "mail (firm note, Vercel text)" default
row NOTIFY_EMAIL           "access-request alerts and digest recipient" secret
row RESEND_API_KEY         "digest / alert mail (Resend)" secret
row TELEGRAM_BOT_TOKEN     "bot (Vercel name: sinder_desk_bot); bot on only with the secret below" secret
row TELEGRAM_WEBHOOK_SECRET "bot: must be the SAME value as on Vercel" secret
row VAPID_PRIVATE_KEY      "web push (pairs with the Vercel public key)" secret
row VAPID_PUBLIC_KEY       "web push (Vercel public key)" default
row VAPID_SUBJECT          "web push contact (optional; code default)" secret
row CRON_SECRET            "scheduled jobs (server's own; cutover-switch generates it)" auto
row TEAM_USER              "optional team login" secret
row TEAM_PASSCODE          "optional team login" secret
row ANTHROPIC_WORKSPACE_ID "optional (AI usage report)" secret
row DATA_BASE_URL          "set by compose to the internal data service; Vercel's value not needed" compose
echo
OPTIONAL=" SERVER_VAPID_SUBJECT SERVER_TEAM_USER SERVER_TEAM_PASSCODE SERVER_ANTHROPIC_WORKSPACE_ID "
REQ=(); OPT=()
for m in "${MUST[@]:-}"; do [ -n "$m" ] || continue; case "$OPTIONAL" in *" $m "*) OPT+=("$m");; *) REQ+=("$m");; esac; done
echo "== repository secrets the owner must add: ${REQ[*]:-none}"
echo "== optional: ${OPT[*]:-none}"
[ "$RUN_ENV" = 1 ] && echo "== some secrets exist but are not in the server .env yet: run the server-env task" || true
REQUIRED_MISSING=""
for k in GOOGLE_SERVICE_ACCOUNT_JSON ANTHROPIC_API_KEY WEB_INDEX_KEY; do [ "$(st "$k")" = set ] || REQUIRED_MISSING+="$k "; done
echo "== cutover-switch would refuse for missing required keys: ${REQUIRED_MISSING:-none}"
mail=off; [ "$(st ZOHO_SMTP_USER)" = set ] && [ "$(st ZOHO_SMTP_PASS)" = set ] && [ "$(st SEND_APPROVERS)" = set ] && mail=on
tg=off; { [ "$(st TELEGRAM_BOT_TOKEN)" = set ] || [ "$(st sinder_desk_bot)" = set ]; } && [ "$(st TELEGRAM_WEBHOOK_SECRET)" = set ] && tg=on
push=off; [ "$(st VAPID_PRIVATE_KEY)" = set ] && push=on
echo "== with the .env as it is now, production mode would run with: mail $mail, telegram $tg, web push $push, cron on"
