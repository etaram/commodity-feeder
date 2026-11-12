// Mail off (AGENT_MAIL_LIVE=0, as in the staging environment): the one mailer every path ends in opens no connection.
// A socket opened during the call would be a failure of this test.
import net from "net";
import tls from "tls";
import { mailReady, sendMail } from "@/lib/mailer";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
(async () => {
  let opened = 0;
  const n0 = net.connect, t0 = tls.connect;
  (net as { connect: unknown }).connect = (...a: unknown[]) => { opened++; return (n0 as (...x: unknown[]) => unknown)(...a); };
  (tls as { connect: unknown }).connect = (...a: unknown[]) => { opened++; return (t0 as (...x: unknown[]) => unknown)(...a); };
  process.env.ZOHO_SMTP_USER = "desk@example.test"; process.env.ZOHO_SMTP_PASS = "not-a-real-password";
  process.env.AGENT_MAIL_LIVE = "0";
  ok(mailReady() === false, "with AGENT_MAIL_LIVE=0 the mailbox reports not ready even when its credentials are set");
  const r = await sendMail({ to: "someone@example.test", subject: "s", text: "t" });
  ok(r.ok === false && r.stage === "config" && opened === 0, "sendMail returns at the config stage and opens no connection");
  process.exit(fail ? 1 : 0);
})();
