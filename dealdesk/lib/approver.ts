// Who may approve an outgoing message (F14). The shared team login is one password known to several people, so an
// approval made with it does not say which person approved. With SEND_APPROVERS set (a comma list of personal account
// e-mails), an approval counts only when it comes from a listed personal account that is an active admin of the
// original workspace; the shared team login, an admin who is not listed, a disabled account and another workspace are
// all refused. Without SEND_APPROVERS the earlier rule stands (any admin of the original workspace, the team login
// included), so switching this on is one environment variable and switching it off is removing it.
// No fallback on a failed Users read: when the account cannot be read, the approval is refused.
import { findUser } from "./users";

export type ApproverUser = { status: string; role: string; workspace?: string } | null;
export type ApproverVerdict = { ok: boolean; enforced: boolean; reason: "" | "not_listed" | "shared_login" | "no_personal_account" | "inactive" | "not_admin" | "other_workspace" | "users_unreadable" };

export const approverList = (env = process.env.SEND_APPROVERS) =>
  String(env || "").split(/[\s,;]+/).map((x) => x.trim().toLowerCase()).filter((x) => /@/.test(x));

// Pure decision. user = the account's row in the Users tab (null when there is none), "unreadable" when the read failed.
export function approverVerdict(email: string, user: ApproverUser | "unreadable", env = process.env.SEND_APPROVERS, teamUser = process.env.TEAM_USER): ApproverVerdict {
  const list = approverList(env), e = String(email || "").trim().toLowerCase();
  if (!list.length) return { ok: true, enforced: false, reason: "" };
  const no = (reason: ApproverVerdict["reason"]): ApproverVerdict => ({ ok: false, enforced: true, reason });
  const team = String(teamUser || "").trim().toLowerCase();
  if (!e) return no("not_listed");
  if (user === "unreadable") return no("users_unreadable");
  // the team login has no row of its own: a session under that name without a personal row is the shared login,
  // even when somebody put the same name on the list
  if (!user) return no(team && e === team ? "shared_login" : "no_personal_account");
  if (!list.includes(e)) return no("not_listed");
  if (user.status !== "active") return no("inactive");
  if (user.role !== "admin") return no("not_admin");
  if (user.workspace && user.workspace !== "sinder") return no("other_workspace");
  return { ok: true, enforced: true, reason: "" };
}

export const APPROVER_REFUSAL = "Only the owner's personal account can approve a message. The shared team login cannot.";

// Fresh read on every decision: a disabled account or a lowered role loses the right at once.
export async function mayApprove(email: string): Promise<ApproverVerdict> {
  if (!approverList().length) return { ok: true, enforced: false, reason: "" };
  const u = await findUser(email, true).then((x) => x as ApproverUser, () => "unreadable" as const);
  return approverVerdict(email, u);
}
