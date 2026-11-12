// F14 through the real handler of POST /api/panel/sendmail, the real gate(), users and send guard, and a signed test session. Only
// next/headers, the sheet, the model and the mailer are in-memory fakes (tests/build-agent-test.mjs): no
// network, no password, nothing leaves. With SEND_APPROVERS set: team login, an unlisted admin, a disabled owner and
// another workspace get 403 and the mailer is never called; the owner's personal account reaches the send.
import { NextRequest } from "next/server";
import { signSession } from "@/lib/auth";
import { JAR } from "./mocks/next-headers";
import { TABS } from "./mocks/sheets-isolation";
import { MAIL } from "./mocks/mailer";
import { POST } from "@/app/api/panel/sendmail/route";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.AUTH_SECRET = "test-secret";
process.env.GOOGLE_SERVICE_ACCOUNT_JSON = "{}";
process.env.TEAM_USER = "team";
const OWNER = "owner@sinder.test";
const user = (email: string, role: string, status: string, ws = "") => [email, email, role, status, "", "password", "", "", "", "", "", "", ws];
const setUsers = (...u: string[][]) => { TABS["Users"] = u; };
const as = (email: string, role: "viewer" | "analyst" | "admin", ws = "sinder") => { JAR.dd_session = signSession(email, role, email, 1, ws); };
let n = 0;
const send = async () => {
  const r = await POST(new NextRequest("http://localhost/api/panel/sendmail", { method: "POST", headers: { "content-type": "application/json" },
    body: JSON.stringify({ to: "buyer@example.test", subject: "Test", body: "Hello", request_id: `t${++n}` }) }));
  return { status: r.status, j: (await r.json().catch(() => ({}))) as Record<string, any> };  // eslint-disable-line @typescript-eslint/no-explicit-any
};

(async () => {
  MAIL.ready = true;
  process.env.SEND_APPROVERS = OWNER;
  setUsers(user(OWNER, "admin", "active"), user("second@sinder.test", "admin", "active"), user("client@acme.test", "admin", "active", "acme"));

  as("team", "admin");
  let r = await send();
  ok(r.status === 403 && r.j.code === "not_approver" && MAIL.sent.length === 0, "shared team login: 403 not_approver, nothing sent");
  as("second@sinder.test", "admin");
  r = await send();
  ok(r.status === 403 && r.j.code === "not_approver" && MAIL.sent.length === 0, "another admin, not listed: 403, nothing sent");
  as("client@acme.test", "admin", "acme");
  r = await send();
  ok(r.status === 403 && MAIL.sent.length === 0, "admin of another workspace: 403, nothing sent");
  as("ghost@sinder.test", "admin");
  r = await send();
  ok(r.status === 403 && MAIL.sent.length === 0, "a signed admin token with no account row: 403, nothing sent");

  as(OWNER, "admin");
  r = await send();
  ok(r.status === 200 && r.j.ok === true && MAIL.sent.length === 1, "the owner's personal account: the message goes to the mailer once");

  // revoked after that: the same signed token no longer approves
  setUsers(user(OWNER, "admin", "disabled"));
  r = await send();
  ok((r.status === 401 || r.status === 403) && MAIL.sent.length === 1, "owner account disabled afterwards: refused, nothing more sent");
  setUsers(user(OWNER, "analyst", "active"));
  r = await send();
  ok((r.status === 401 || r.status === 403) && MAIL.sent.length === 1, "owner lowered to analyst: refused, nothing more sent");

  // the variable removed: the earlier rule (migration only) and the team login sends again; this is why production
  // is not counted as safe while the variable is missing
  delete process.env.SEND_APPROVERS;
  setUsers(user(OWNER, "admin", "active"));
  as("team", "admin");
  r = await send();
  ok(r.status === 200 && MAIL.sent.length === 2, "without SEND_APPROVERS the team login still sends (old rule, recorded here on purpose)");
  process.exit(fail ? 1 : 0);
})();
