// Password reset links: valid once (bound to the current password hash), for 30 minutes, signed with AUTH_SECRET.
process.env.AUTH_SECRET = "t".repeat(40);
import { checkReset, resetEmail, resetToken } from "@/lib/reset";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const t = resetToken("owner@sinder.pro", "s1$a$b");
ok(resetEmail(t) === "owner@sinder.pro", "the link names the account");
ok(checkReset(t, "s1$a$b").ok, "a fresh link is valid");
ok(!checkReset(t, "s1$c$d").ok, "after the password changed the old link is refused (single use)");
const late = checkReset(t, "s1$a$b", Date.now() + 31 * 60e3);
ok(!late.ok && late.why === "expired", "after 30 minutes the link has expired");
ok(!checkReset(t.slice(0, -2) + "xx", "s1$a$b").ok, "a changed signature is refused");
const forged = Buffer.from(`other@x.io|${Date.now() + 1e6}`).toString("base64url") + "." + t.split(".")[1];
ok(!checkReset(forged, "s1$a$b").ok, "another address with a copied signature is refused");
ok(!checkReset("", "").ok && !checkReset("abc", "").ok, "garbage is refused");
if (fail) { console.log(`${fail} failed`); process.exit(1); }
