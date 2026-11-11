// What the audit session (header x-dd-audit, see lib/gate.ts) may call. The self-check and the UI audit only read,
// but the audit session carries the admin role so it can read the admin views; without this list a leaked audit
// token could send mail from the owner's mailbox or change who has access. Pure and edge-safe: the middleware
// applies it to every request that arrives with the audit header, before any route runs.
// Never, whatever the method: routes whose only purpose is to send, to start the agent or to hand out a key.
const NEVER = ["/api/panel/sendmail", "/api/outreach/authorize", "/api/mcp/key"];
// Reading allowed (the self-check reads these), writing never: the sending queue, replies and campaign control, the
// agent, users, the bot setup, deal and client records, decisions, queued and instant research jobs, admin actions.
const READ_ONLY = ["/api/outreach/", "/api/agent/", "/api/users", "/api/telegram/", "/api/push", "/api/clients", "/api/deal", "/api/missions", "/api/decision", "/api/job", "/api/panel/admin", "/api/panel/append", "/api/panel/run"];
const under = (path: string, p: string) => path === p || (p.endsWith("/") ? path.startsWith(p) : path.startsWith(p + "/"));
export function auditMayCall(method: string, pathname: string): boolean {
  const path = pathname.replace(/\/+$/, "") || "/", m = (method || "GET").toUpperCase();
  if (NEVER.some((p) => path === p)) return false;
  // the panel reads through POST on many routes (get, search, suppliers-for, know), so POST as such stays open
  if (m !== "GET" && m !== "HEAD" && READ_ONLY.some((p) => under(path, p))) return false;
  return true;
}
