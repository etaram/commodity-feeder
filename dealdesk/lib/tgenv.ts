// The bot token and username. Preferred: TELEGRAM_BOT_TOKEN and TELEGRAM_BOT_USERNAME. Also accepted: a variable
// named after the bot itself (key "sinder_desk_bot" holding the token), which is how it was first entered.
// TELEGRAM_OFF=1 hides the token from the whole app: a second instance (the server copy while the live site and its
// webhook stay on Vercel) then never registers the webhook, never answers updates and never sends to the bot.
export function tgEnv(): { token: string; username: string } {
  if (process.env.TELEGRAM_OFF === "1") return { token: "", username: "" };
  let token = process.env.TELEGRAM_BOT_TOKEN || "", username = process.env.TELEGRAM_BOT_USERNAME || "";
  if (!token) {
    for (const [k, v] of Object.entries(process.env)) {
      if (/_?bot$/i.test(k) && v && /^\d{6,}:[A-Za-z0-9_-]{30,}$/.test(v)) { token = v; username = username || k; break; }
    }
  }
  return { token, username };
}
