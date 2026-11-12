# Sourced by the root scripts of the server instance (server-up, server-env, cutover-*). One place decides how the
# instance runs: the isolated test mode (docker-compose.server.yml alone) unless /opt/sinder/server-mode says
# "production" (written by cutover-switch, removed by cutover-rollback); then docker-compose.server.prod.yml is layered
# on top, with the server .env as --env-file for its ${...} values. Every script that recreates the instance goes
# through server_compose, so a later server-up or server-env never flips the mode by accident.
SERVER_MODE_FILE=/opt/sinder/server-mode
SERVER_ENV_FILE=/opt/sinder/repo/deploy/.env
server_mode() { [ "$(cat "$SERVER_MODE_FILE" 2>/dev/null)" = production ] && echo production || echo test; }
server_compose_prod() { (cd /opt/sinder/server-instance/deploy && docker compose -p sinder-server --env-file "$SERVER_ENV_FILE" -f docker-compose.server.yml -f docker-compose.server.prod.yml "$@"); }
server_compose_test() { (cd /opt/sinder/server-instance/deploy && docker compose -p sinder-server -f docker-compose.server.yml "$@"); }
server_compose() { if [ "$(server_mode)" = production ]; then server_compose_prod "$@"; else server_compose_test "$@"; fi; }
# set | empty | missing for one key of the server .env (never the value); "# comment" alone counts as empty
env_state() { if grep -qE "^$1=" "$SERVER_ENV_FILE"; then v=$(grep -E "^$1=" "$SERVER_ENV_FILE" | tail -1 | cut -d= -f2- | sed -E 's/^[[:space:]]*#.*$//; s/[[:space:]]+$//; s/^[[:space:]]+//')
  [ -n "$v" ] && echo set || echo empty; else echo missing; fi; }
env_has() { [ "$(env_state "$1")" = set ]; }
# the bot token: TELEGRAM_BOT_TOKEN, or the variable named after the bot (as on Vercel: sinder_desk_bot)
tg_token_set() { env_has TELEGRAM_BOT_TOKEN || env_has sinder_desk_bot; }
# A records of desk.sinder.pro from two public resolvers (DNS over HTTPS), one line each: "<resolver> <answers>"
DESK_PUBLIC=desk.sinder.pro; SERVER_IP=216.158.234.218
dns_answers() { curl -s --max-time 10 -H 'accept: application/dns-json' "$1?name=$DESK_PUBLIC&type=A" | grep -oE '"data":"[^"]*"' | cut -d'"' -f4 | tr '\n' ' '; }
dns_points_here() { # true only when both resolvers answer with exactly this server's address and nothing else
  for r in https://cloudflare-dns.com/dns-query https://dns.google/resolve; do a=$(dns_answers "$r"); [ "$(echo $a)" = "$SERVER_IP" ] || return 1; done; }
# Telegram: one Bot API call from inside the app container, with the token from the container's own environment (never
# printed, never on a command line). Prints the webhook host only, the pending count and whether there is a last error.
tg_call() { docker exec -i -e TG_METHOD="$1" -e TG_URL="${2:-}" sinder-server-app node - <<'JS' 2>&1 | tail -3
const tok = process.env.TELEGRAM_BOT_TOKEN || Object.entries(process.env).find(([k, v]) => /_?bot$/i.test(k) && /^\d{6,}:[A-Za-z0-9_-]{30,}$/.test(v || ""))?.[1] || "";
const api = (m, b) => fetch(`https://api.telegram.org/bot${tok}/${m}`, b ? { method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(b) } : undefined).then((r) => r.json());
(async () => {
  if (!tok) return console.log("telegram: no bot token in the container");
  if (process.env.TG_METHOD === "set") {
    if (!process.env.TELEGRAM_WEBHOOK_SECRET) return console.log("telegram: TELEGRAM_WEBHOOK_SECRET not set: webhook NOT changed");
    const r = await api("setWebhook", { url: process.env.TG_URL, secret_token: process.env.TELEGRAM_WEBHOOK_SECRET, allowed_updates: ["message", "edited_message", "callback_query"], drop_pending_updates: false });
    console.log("setWebhook: " + (r.ok ? "ok" : "FAILED " + String(r.description || "").slice(0, 80)));
  }
  const h = (await api("getWebhookInfo")).result || {};
  let host = ""; try { host = h.url ? new URL(h.url).host : "(none)"; } catch { host = "(unparsable)"; }
  console.log(`webhook host: ${host}   pending: ${h.pending_update_count ?? "?"}   last error: ${h.last_error_message ? "yes (" + String(h.last_error_message).slice(0, 60) + ")" : "none"}`);
})().catch((e) => console.log("telegram: ERR " + String(e.message || e).slice(0, 80)));
JS
}
