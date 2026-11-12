// F14: with SEND_APPROVERS set, only the listed personal account approves an outgoing message; the shared team login
// and every other session are refused. Pure decision, no network.
import { approverList, approverVerdict } from "@/lib/approver";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const admin = { status: "active", role: "admin", workspace: "" };
const LIST = "Owner@Sinder.pro", TEAM = "team";
const v = (email: string, user: Parameters<typeof approverVerdict>[1], list = LIST, team = TEAM) => approverVerdict(email, user, list, team);

ok(approverList(" a@x.io, B@x.io;junk ").join() === "a@x.io,b@x.io", "the list is read from the variable, lower case, addresses only");
// not configured: the earlier rule stands and the caller is told it is not enforced
ok(v("team", null, "").ok && !v("team", null, "").enforced, "without SEND_APPROVERS nothing changes and enforced=false is reported");
// positive
ok(v("owner@sinder.pro", admin).ok && v("OWNER@sinder.pro", admin).enforced, "the listed personal admin account approves");
ok(v("owner@sinder.pro", { ...admin, workspace: "sinder" }).ok, "the original workspace written out is the same workspace");
// negatives
let r = v("team", null);
ok(!r.ok && r.reason === "shared_login", "the shared team login is refused");
r = v("team", null, "team, owner@sinder.pro");
ok(!r.ok, "the shared team login is refused even when its name is put on the list (not an address)");
r = v("team@sinder.pro", null, "team@sinder.pro", "team@sinder.pro");
ok(!r.ok && r.reason === "shared_login", "a team login that is an address and is listed is still refused: it has no personal account");
r = v("owner@sinder.pro", null);
ok(!r.ok && r.reason === "no_personal_account", "a listed address without a Users row is refused (a forged or legacy token)");
r = v("second@sinder.pro", admin);
ok(!r.ok && r.reason === "not_listed", "another admin who is not listed is refused");
r = v("owner@sinder.pro", { ...admin, status: "disabled" });
ok(!r.ok && r.reason === "inactive", "the owner's account, once disabled, is refused");
r = v("owner@sinder.pro", { ...admin, role: "analyst" });
ok(!r.ok && r.reason === "not_admin", "a lowered role is refused");
r = v("owner@sinder.pro", { ...admin, workspace: "client-a" });
ok(!r.ok && r.reason === "other_workspace", "another workspace is refused");
r = v("owner@sinder.pro", "unreadable");
ok(!r.ok && r.reason === "users_unreadable", "when the Users tab cannot be read the approval is refused, not waved through");
ok(!v("", admin).ok, "an empty session address is refused");
process.exit(fail ? 1 : 0);
