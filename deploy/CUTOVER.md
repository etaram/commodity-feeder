# Moving desk.sinder.pro from Vercel to our server

The server instance (compose project `sinder-server`, https://desk.216-158-234-218.sslip.io) runs isolated today:
staging sheet, mail off, bot off, no cron. The move flips it to production mode. Vercel stays as the fallback.
All tasks below run from Actions > server-ops (branch `release/server`). None of them touches Vercel or DNS.

## Before the day

1. Run `cutover-prepare`. It changes nothing. It prints which keys production mode needs, which are in the server
   `.env` (names only), which repository secrets exist, and the exact list of secrets still to add.
2. Owner adds the listed repository secrets (Settings > Secrets and variables > Actions), named `SERVER_<KEY>`.
   Values are in Vercel > Project > Settings > Environment Variables. Sensitive ones cannot be read back there
   (for example `ZOHO_SMTP_PASS`): take them from where they were created. `SERVER_TELEGRAM_WEBHOOK_SECRET` must be
   the same value as Vercel's `TELEGRAM_WEBHOOK_SECRET`; `SERVER_TELEGRAM_BOT_TOKEN` is Vercel's `sinder_desk_bot`.
3. Run `server-env` (copies the secrets into the server `.env`, still in test mode), then `cutover-prepare` again
   until nothing required is missing.
4. Owner lowers the TTL of the `desk` record at IONOS to 300 seconds, a day ahead.

Sign-in: the server keeps its own `AUTH_SECRET`. After the move everyone signs in once more, and MCP addresses
(derived from `AUTH_SECRET`) change: take the new one from the panel. This is accepted.

## The switch (pick a time outside 04:20-07:00 UTC, when the daily jobs run)

1. Owner, at IONOS: replace the CNAME `desk` -> `885ac5094c24289e.vercel-dns-017.com` with an A record
   `desk` -> `216.158.234.218`.
2. Wait until public DNS shows the new address (`cutover-switch` checks Cloudflare and Google and refuses otherwise).
3. Run `cutover-switch`. It: puts the instance in production mode (live state sheet, no read-only sheets, `DESK_ENV=production`),
   turns mail on only if `ZOHO_SMTP_USER`, `ZOHO_SMTP_PASS` and `SEND_APPROVERS` are all set, turns the bot on only if
   token and webhook secret are set, starts the cron service against the server app, adds the `desk.sinder.pro` site
   block to the gateway Caddy (the sslip name stays), sets the Telegram webhook (same URL and secret), and prints:
   `/login` 200 with a valid certificate, `/api/staging-check` 404, webhook host.
4. In the same minute, on Vercel (owner or Claude):
   - set `AGENT_MAIL_LIVE=0` for Production, so the old site can never send mail;
   - disable the cron jobs (Project > Settings > Cron Jobs > Disable, or a commit on `main` that empties `crons` in
     `dealdesk/vercel.json`);
   - redeploy production so both take effect.
   Do not remove the domain or the project from Vercel: it is the fallback.
5. Check: sign in at https://desk.sinder.pro, send `/help` to the bot, run `server-logs`.

## Rollback

1. Owner, at IONOS: put the CNAME `desk` -> `885ac5094c24289e.vercel-dns-017.com` back.
2. Run `cutover-rollback`: removes the production mode and the cron service, removes the `desk.sinder.pro` site block,
   recreates the app isolated (staging sheet, mail off, bot off) and prints the webhook host.
3. Webhook: the URL is `https://desk.sinder.pro/api/telegram` in both setups, so with DNS back it lands on Vercel by
   itself. Only if the bot stays silent: an admin presses the Telegram setup on the Vercel site (`POST /api/telegram/setup`).
4. On Vercel: set `AGENT_MAIL_LIVE` back (remove it), re-enable the crons, redeploy.

Nothing is lost by a rollback: the server writes to the same live sheets Vercel uses, so every change made on the
server after the switch is already where Vercel reads it.
