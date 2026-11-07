import { asWs } from "@/lib/auth";
import { audienceKey, iso, logEvent, needsReauthorization, put, readAccounts, readCampaign, engineMove, type Ctx } from "./campaign";
import { passes, renderMessage, validateMessage } from "./draft";
import { handleReply, logRows, type Deps } from "./outbox";
import { latest, sha, type Snapshot } from "./store";
import { isSuppressed } from "./suppression";
import type { LinkedInTask, ReplyCategory } from "./types";

// LinkedIn: NO automation. The engine only prepares a queue of tasks a person executes by hand in LinkedIn
// (prospect research, approved connection-note and message drafts) and records what that person logs back.
// Nothing here calls LinkedIn or any other outside service.

const CONNECT_NOTE_MAX = 300;

export function linkedinTasks(snap: Snapshot, ws: string, campaignId?: string): LinkedInTask[] {
  return [...latest(snap.linkedin, ws).values()].map((r) => ({ ...(r.data as unknown as LinkedInTask), status: r.status as LinkedInTask["status"] }))
    .filter((t) => !campaignId || t.campaign_id === campaignId).sort((a, b) => a.created_at.localeCompare(b.created_at));
}

// Creates (idempotently) a prospect task and a connection or message task with an approved draft for each
// authorized account that has a LinkedIn profile. Drafts come from the campaign's authorized LinkedIn templates.
export async function generateLinkedInTasks(ctx: Ctx, ws: string, campaignId: string, by: string): Promise<{ created: number; skipped: { account_id: string; reason: string }[] }> {
  ws = asWs(ws);
  const snap = await ctx.store.load();
  const c = readCampaign(snap, ws, campaignId);
  if (!c) throw new Error("campaign not found");
  if (!["authorized", "running"].includes(c.status)) throw new Error(`campaign is ${c.status}; drafts must be authorized first`);
  if (needsReauthorization(c)) throw new Error("the scope changed since authorization: re-authorize first");
  const existing = latest(snap.linkedin, ws);
  const aud = new Set(c.authorization!.audience);
  let created = 0;
  const skipped: { account_id: string; reason: string }[] = [];
  for (const a of readAccounts(snap, ws, c.id)) {
    if (!aud.has(audienceKey(a))) continue;
    if (!a.linkedin_url) { skipped.push({ account_id: a.id, reason: "no LinkedIn profile URL" }); continue; }
    if (a.stage === "closed") { skipped.push({ account_id: a.id, reason: "account closed" }); continue; }
    if (a.email && isSuppressed(snap, ws, a.email, c.id)) { skipped.push({ account_id: a.id, reason: "suppressed" }); continue; }
    const kinds: { kind: LinkedInTask["kind"]; draft: string }[] = [{ kind: "prospect", draft: "" }];
    for (const k of ["connect", "message"] as const) {
      const r = renderMessage(c.plan, a, 0, "linkedin", k);
      if (r.template_id === "") continue;
      const checks = validateMessage({ subject: "", body: r.body, from_email: "", from_name: c.plan.sender.name }, c.plan, "linkedin");
      if (k === "connect" && r.body.length > CONNECT_NOTE_MAX) checks.push({ name: "connect_note_length", ok: false, detail: `over ${CONNECT_NOTE_MAX} chars` });
      if (r.errors.length || !passes(checks)) { skipped.push({ account_id: a.id, reason: `${k} draft failed: ${[...r.errors, ...checks.filter((x) => !x.ok).map((x) => x.name)].join(", ")}` }); continue; }
      kinds.push({ kind: k, draft: r.body });
    }
    for (const k of kinds) {
      const id = `LI-${sha(`${ws}|${c.id}|${a.id}|${k.kind}`).slice(0, 14)}`;
      if (existing.has(id)) continue;
      const t: LinkedInTask = {
        id, ws, campaign_id: c.id, account_id: a.id, kind: k.kind, status: "open", profile_url: a.linkedin_url, company: a.company,
        contact_name: a.contact_name, draft: k.draft, interaction: "", outcome: "", note: "", done_by: "", done_at: "", created_at: iso(ctx.now()),
      };
      await put(ctx, "linkedin", { ws, campaign_id: c.id, id, status: "open", data: t, by });
      created++;
    }
  }
  return { created, skipped };
}

export const INTERACTIONS = ["profile_viewed", "connection_sent", "connection_accepted", "message_sent", "reply_received", "meeting_booked", "not_done"] as const;
export type Interaction = (typeof INTERACTIONS)[number];

// A person logs what they did by hand. Contact interactions count toward cross-channel recent-contact checks;
// a reply is handled with the same stop rules as an email reply (category chosen by the person, or classified).
export async function logLinkedInTask(deps: Deps, ws: string, req: { task_id: string; status: "done" | "skipped"; interaction: Interaction; note?: string; reply_text?: string; reply_category?: ReplyCategory }, by: string) {
  ws = asWs(ws);
  const snap = await deps.store.load();
  const r = latest(snap.linkedin, ws).get(req.task_id);
  if (!r) throw new Error("task not found");
  if (!INTERACTIONS.includes(req.interaction)) throw new Error("unknown interaction");
  const t = { ...(r.data as unknown as LinkedInTask), status: req.status, interaction: req.interaction, note: String(req.note || "").slice(0, 1000), done_by: by, done_at: iso(deps.now()) };
  await put(deps, "linkedin", { ws, campaign_id: t.campaign_id, id: t.id, status: t.status, data: t, by });
  const a = readAccounts(snap, ws, t.campaign_id).find((x) => x.id === t.account_id);
  const contact = ["connection_sent", "message_sent"].includes(req.interaction);
  await logEvent(deps, ws, t.campaign_id, contact ? "linkedin_contact" : req.interaction === "meeting_booked" ? "meeting" : req.interaction === "reply_received" ? "linkedin_reply_logged" : "linkedin_activity",
    { account_id: t.account_id, task_id: t.id, interaction: req.interaction, linkedin_url: t.profile_url, to: a?.email || "", note: t.note.slice(0, 300), channel: "linkedin" }, by);
  let reply = null;
  let acc = a;
  if (acc && contact && acc.stage === "outreach_authorized") acc = await engineMove(deps, acc, "contacted", `LinkedIn ${req.interaction}`, by);
  if (acc && req.interaction === "meeting_booked") acc = await engineMove(deps, acc, "qualified", "meeting booked (LinkedIn)", by);
  if (a && req.interaction === "reply_received") {
    reply = await handleReply(deps, ws, { campaign_id: t.campaign_id, account_id: a.id, text: String(req.reply_text || ""), channel: "linkedin", category: req.reply_category }, by);
  }
  return { task: t, reply };
}

// Cross-channel contact history for one account (email sends, replies, LinkedIn interactions, stage moves).
export function contactHistory(snap: Snapshot, ws: string, accountId: string) {
  return logRows(snap, ws, { account_id: accountId }).map((r) => {
    const d = r.data as Record<string, unknown>;
    return { at: String(d.at || r.time), campaign_id: r.campaign_id, kind: r.status, channel: String(d.channel || (r.status.startsWith("linkedin") ? "linkedin" : "email")), detail: String(d.category || d.interaction || d.reason || d.subject || d.to || "").slice(0, 200), by: r.by };
  });
}
