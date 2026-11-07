import { asWs } from "@/lib/auth";
import {
  audienceKey, cancelQueued, iso, killSwitch, logEvent, needsReauthorization, planHash, put, readAccounts, readCampaign,
  scopeSummary, writeAccount, writeCampaign, engineMove, CONTROL_ID, canMoveCampaign, type Ctx,
} from "./campaign";
import { classifyReply, replyEffect, type ClassifyModel } from "./classify";
import { adaptWording, passes, renderMessage, validateAdaptation, validateMessage, withFooter, type ModelFn } from "./draft";
import { inWs, latest, sha, type Row, type Snapshot } from "./store";
import { addSuppression, isSuppressed } from "./suppression";
import { classifySendError, type Transport } from "./transport";
import type { Account, Campaign, OutboxItem, ReplyCategory } from "./types";

// Queued outbox with idempotency keys, rate limits, retry classification and every pre-send check, plus the
// campaign controls (start, pause, resume, cancel, withdraw) and the per-workspace emergency stop.
// tick() does nothing unless OUTREACH_ENABLED=1 (or enabled:true is passed by a test).

export type Deps = Ctx & { transport: Transport; adaptModel?: ModelFn; classifyModel?: ClassifyModel };

const HOUR = 3600e3, DAY = 864e5;
export const MAX_ATTEMPTS = 3;
export const STUCK_SENDING_MS = 10 * 60e3;
const wsHourlyCap = () => { const n = Number(process.env.OUTREACH_WS_HOURLY); return Number.isFinite(n) && n > 0 ? Math.min(200, n) : 30; };

export const idemKeyFor = (ws: string, campaignId: string, accountId: string, step: number) => sha(`${asWs(ws)}|${campaignId}|${accountId}|${step}`).slice(0, 32);

export function outboxItems(snap: Snapshot, ws: string, campaignId?: string): OutboxItem[] {
  return [...latest(snap.outbox, ws).values()].map((r) => ({ ...(r.data as unknown as OutboxItem), status: r.status as OutboxItem["status"] }))
    .filter((x) => !campaignId || x.campaign_id === campaignId).sort((a, b) => a.due_at.localeCompare(b.due_at));
}
export function logRows(snap: Snapshot, ws: string, f: { campaign_id?: string; account_id?: string } = {}): Row[] {
  return inWs(snap.log, ws).filter((r) => (!f.campaign_id || r.campaign_id === f.campaign_id) && (!f.account_id || (r.data as Record<string, unknown>).account_id === f.account_id))
    .sort((a, b) => b.rev.localeCompare(a.rev));
}

async function writeItem(ctx: Ctx, it: OutboxItem, by = "system") {
  await put(ctx, "outbox", { ws: it.ws, campaign_id: it.campaign_id, id: it.id, status: it.status, data: it, by });
}

// ---------------- enqueue ----------------

export async function enqueue(deps: Deps, ws: string, req: { campaign_id: string; account_id: string; step: number; due_at?: string; idem_key?: string }, by: string, snap?: Snapshot): Promise<{ item: OutboxItem; created: boolean }> {
  ws = asWs(ws);
  snap ||= await deps.store.load();
  const c = readCampaign(snap, ws, req.campaign_id);
  if (!c) throw new Error("campaign not found");
  if (!["authorized", "running", "paused"].includes(c.status)) throw new Error(`campaign is ${c.status}`);
  if (c.plan.channel !== "email") throw new Error("only email campaigns use the outbox; LinkedIn is a human task queue");
  const acc = readAccounts(snap, ws, c.id).find((a) => a.id === req.account_id);
  if (!acc) throw new Error("account not found");
  const key = (req.idem_key || idemKeyFor(ws, c.id, acc.id, req.step)).slice(0, 64);
  const existing = outboxItems(snap, ws).find((x) => x.idem_key === key);
  if (existing) return { item: existing, created: false };
  const r = renderMessage(c.plan, acc, req.step, "email");
  if (r.errors.length) throw new Error(`draft failed: ${r.errors.join("; ")}`);
  let adapted: OutboxItem["adapted"] = null;
  if (c.plan.adapt_wording && deps.adaptModel) adapted = (await adaptWording(c.plan, acc, req.step, deps.adaptModel)).adapted;
  const now = iso(deps.now());
  const item: OutboxItem = {
    id: `OB-${sha(`${ws}|${key}`).slice(0, 16)}`, ws, campaign_id: c.id, account_id: acc.id, step: req.step, idem_key: key,
    status: "queued", reason: "", due_at: req.due_at || now, attempts: 0, last_error: "",
    to: acc.email, from_email: c.plan.sender.email, from_name: c.plan.sender.name, subject: r.subject, body: r.body,
    attachments: c.plan.attachments, claims_used: r.claims_used, template_id: r.template_id,
    plan_hash: planHash(c.plan), adapted, created_at: now, created_by: by, sent_at: "", provider_id: "", transport: "",
  };
  await writeItem(deps, item, by);
  return { item, created: true };
}

// ---------------- campaign controls ----------------

type Res = { ok: true; campaign: Campaign; enqueued?: number; cancelled?: number } | { ok: false; error: string };

export async function startCampaign(deps: Deps, ws: string, id: string, by: string): Promise<Res> {
  ws = asWs(ws);
  const snap = await deps.store.load();
  const c = readCampaign(snap, ws, id);
  if (!c) return { ok: false, error: "campaign not found" };
  if (killSwitch(snap, ws).engaged) return { ok: false, error: "the workspace emergency stop is engaged" };
  if (!["authorized", "paused"].includes(c.status)) return { ok: false, error: `cannot start a ${c.status} campaign` };
  if (needsReauthorization(c)) return { ok: false, error: "the scope changed since authorization: re-authorize first" };
  const next: Campaign = { ...c, status: "running", status_reason: `started by ${by}` };
  await writeCampaign(deps, next, by);
  let enqueued = 0;
  if (c.plan.channel === "email") {
    const aud = new Set(c.authorization!.audience);
    const fresh = await deps.store.load();
    for (const a of readAccounts(fresh, ws, c.id)) {
      if (a.stage !== "outreach_authorized" || !aud.has(audienceKey(a))) continue;
      const r = await enqueue(deps, ws, { campaign_id: c.id, account_id: a.id, step: 0 }, by, fresh).catch(() => null);
      if (r?.created) enqueued++;
    }
  }
  await logEvent(deps, ws, c.id, c.status === "paused" ? "resume" : "start", { enqueued }, by);
  return { ok: true, campaign: next, enqueued };
}

export async function pauseCampaign(deps: Deps, ws: string, id: string, by: string, reason = "paused"): Promise<Res> {
  ws = asWs(ws);
  const c = readCampaign(await deps.store.load(), ws, id);
  if (!c) return { ok: false, error: "campaign not found" };
  if (!canMoveCampaign(c.status, "paused")) return { ok: false, error: `cannot pause a ${c.status} campaign` };
  const next: Campaign = { ...c, status: "paused", status_reason: reason };
  await writeCampaign(deps, next, by);
  await logEvent(deps, ws, c.id, "pause", { reason }, by);
  return { ok: true, campaign: next };
}

async function endCampaign(deps: Deps, ws: string, id: string, to: "cancelled" | "stopped", by: string, reason: string): Promise<Res> {
  ws = asWs(ws);
  const snap = await deps.store.load();
  const c = readCampaign(snap, ws, id);
  if (!c) return { ok: false, error: "campaign not found" };
  if (!canMoveCampaign(c.status, to)) return { ok: false, error: `cannot move a ${c.status} campaign to ${to}` };
  const next: Campaign = { ...c, status: to, status_reason: reason, authorization: to === "stopped" ? null : c.authorization };
  await writeCampaign(deps, next, by);
  const cancelled = await cancelQueued(deps, snap, ws, (d) => d.campaign_id === c.id, `campaign_${to}`, by);
  await logEvent(deps, ws, c.id, to === "cancelled" ? "cancel" : "stop", { reason, cancelled }, by);
  return { ok: true, campaign: next, cancelled };
}
export const cancelCampaign = (d: Deps, ws: string, id: string, by: string, reason = "cancelled") => endCampaign(d, ws, id, "cancelled", by, reason);
// Authorization withdrawal: the campaign stops and needs a new authorization to run again.
export const withdrawAuthorization = (d: Deps, ws: string, id: string, by: string, reason = "authorization withdrawn") => endCampaign(d, ws, id, "stopped", by, reason);

// Global kill switch per workspace: halts every send at once and pauses running campaigns (each needs a resume).
export async function emergencyStop(deps: Deps, ws: string, by: string, reason = "emergency stop"): Promise<{ paused: number }> {
  ws = asWs(ws);
  const at = iso(deps.now());
  await put(deps, "campaigns", { ws, campaign_id: "*", id: CONTROL_ID, status: "engaged", data: { by, at, reason: reason.slice(0, 300) }, by });
  const snap = await deps.store.load();
  let paused = 0;
  for (const r of latest(snap.campaigns, ws).values()) {
    if (r.id === CONTROL_ID) continue;
    const c = r.data as unknown as Campaign;
    if (c.status === "running" || c.status === "authorized") { await writeCampaign(deps, { ...c, status: "paused", status_reason: "emergency_stop" }, by); paused++; }
  }
  await logEvent(deps, ws, "*", "emergency_stop", { reason, paused }, by);
  return { paused };
}
export async function clearEmergencyStop(deps: Deps, ws: string, by: string): Promise<void> {
  ws = asWs(ws);
  await put(deps, "campaigns", { ws, campaign_id: "*", id: CONTROL_ID, status: "clear", data: { by, at: iso(deps.now()), reason: "cleared" }, by });
  await logEvent(deps, ws, "*", "emergency_clear", {}, by);
}

// ---------------- stop conditions ----------------

const STOP_KINDS = new Set(["bounce", "opt_out", "meeting", "linkedin_reply"]);
function stoppedBy(snap: Snapshot, ws: string, c: Campaign, a: Account): string {
  for (const r of logRows(snap, ws, { account_id: a.id })) {
    if (r.campaign_id !== c.id && r.status !== "opt_out" && r.status !== "bounce") continue;
    const d = r.data as Record<string, unknown>;
    if (r.status === "reply" && replyEffect(d.category as ReplyCategory).stop) return `reply_${d.category}`;
    if (STOP_KINDS.has(r.status)) return r.status;
  }
  return "";
}

// Auto stop: too many hard bounces or opt-outs in a campaign stops it (and cancels its queue).
async function autoStop(deps: Deps, ws: string, campaignId: string) {
  const snap = await deps.store.load();
  const c = readCampaign(snap, ws, campaignId);
  if (!c || !["running", "authorized", "paused"].includes(c.status)) return;
  const rows = logRows(snap, ws, { campaign_id: campaignId });
  const cat = (r: Row) => String((r.data as Record<string, unknown>).category || "");
  const bounces = rows.filter((r) => r.status === "bounce" || (r.status === "reply" && cat(r) === "hard_bounce")).length;
  const optOuts = rows.filter((r) => r.status === "reply" && cat(r) === "opt_out").length;
  if (bounces >= c.plan.auto_stop.max_hard_bounces) await withdrawAuthorization(deps, ws, campaignId, "system", `auto stop: ${bounces} hard bounces`);
  else if (optOuts >= c.plan.auto_stop.max_opt_outs) await withdrawAuthorization(deps, ws, campaignId, "system", `auto stop: ${optOuts} opt-outs`);
}

async function closeAccount(deps: Deps, a: Account, reason: string) {
  await engineMove(deps, a, "closed", reason, "system");
}

// ---------------- the tick ----------------

export type TickResult = { id: string; ws: string; action: "sent" | "deferred" | "cancelled" | "failed" | "retry" | "duplicate" | "needs_review"; reason: string };

function sentWithin(snap: Snapshot, ws: string, ms: number, now: number, campaignId?: string): number {
  const since = iso(now - ms);
  return inWs(snap.log, ws).filter((r) => r.status === "sent" && (!campaignId || r.campaign_id === campaignId) && String((r.data as Record<string, unknown>).at || "") >= since).length;
}

async function processItem(deps: Deps, snap: Snapshot, it: OutboxItem): Promise<TickResult> {
  const ws = it.ws, now = deps.now();
  const out = (action: TickResult["action"], reason: string): TickResult => ({ id: it.id, ws, action, reason });
  const defer = async (reason: string) => { if (it.reason !== reason) await writeItem(deps, { ...it, reason }); return out("deferred", reason); };
  const cancel = async (reason: string) => { await writeItem(deps, { ...it, status: "cancelled", reason }); await logEvent(deps, ws, it.campaign_id, "skip", { account_id: it.account_id, outbox_id: it.id, step: it.step, reason }); return out("cancelled", reason); };

  if (killSwitch(snap, ws).engaged) return defer("emergency_stop");
  const c = readCampaign(snap, ws, it.campaign_id);
  if (!c) return cancel("campaign_missing");
  if (c.status === "cancelled" || c.status === "stopped") return cancel(`campaign_${c.status}`);
  if (c.status !== "running") return defer(`campaign_${c.status}`);
  if (!c.authorization) return defer("not_authorized");
  if (planHash(c.plan) !== c.authorization.plan_hash) return defer("scope_changed_reauthorization_required");
  const a = readAccounts(snap, ws, c.id).find((x) => x.id === it.account_id);
  if (!a) return cancel("account_missing");

  const sup = isSuppressed(snap, ws, a.email, c.id) || isSuppressed(snap, ws, it.to, c.id);
  if (sup) { await closeAccount(deps, a, `suppressed: ${sup.reason}`); return cancel(`suppressed: ${sup.reason}`); }
  const stop = stoppedBy(snap, ws, c, a);
  if (stop) return cancel(`stop_condition: ${stop}`);
  const needStage = it.step === 0 ? "outreach_authorized" : "contacted";
  if (a.stage !== needStage) return cancel(`eligibility_changed: account is ${a.stage}`);
  if (a.conflict) return cancel("account_conflict");
  if (!c.authorization.audience.includes(audienceKey(a))) return defer("not_in_authorized_audience");
  if (a.email.toLowerCase() !== it.to.toLowerCase()) return cancel("recipient_changed");

  if (it.step === 0) {
    const since = iso(now - c.plan.recent_contact_days * DAY);
    const recent = inWs(snap.log, ws).find((r) => {
      const d = r.data as Record<string, unknown>;
      if (!["sent", "linkedin_contact"].includes(r.status) || String(d.at || "") < since) return false;
      return (a.email && String(d.to || "").toLowerCase() === a.email.toLowerCase()) || (a.linkedin_url && d.linkedin_url === a.linkedin_url);
    });
    if (recent) return cancel(`recent_contact: ${recent.status} on ${String((recent.data as Record<string, unknown>).at).slice(0, 10)}`);
    const other = outboxItems(snap, ws).find((x) => x.campaign_id !== c.id && x.to.toLowerCase() === it.to.toLowerCase() && ["queued", "sending", "sent"].includes(x.status));
    if (other) return cancel(`account_conflict: also in campaign ${other.campaign_id}`);
  }

  const ident = await deps.transport.verifySender(ws, c.plan.sender.email);
  if (ident === null) return defer("sender_not_verified");
  if (ident !== c.plan.sender.name) return defer("sender_identity_mismatch");

  const dup = inWs(snap.log, ws).some((r) => r.status === "sent" && (r.data as Record<string, unknown>).idem_key === it.idem_key)
    || outboxItems(snap, ws).some((x) => x.idem_key === it.idem_key && x.id !== it.id && ["sent", "sending"].includes(x.status));
  if (dup) { await writeItem(deps, { ...it, status: "cancelled", reason: "duplicate_idempotency_key" }); return out("duplicate", "already sent with this idempotency key"); }

  if (sentWithin(snap, ws, HOUR, now, c.id) >= c.plan.volume.per_hour) return defer("rate_limit_campaign_hour");
  if (sentWithin(snap, ws, DAY, now, c.id) >= c.plan.volume.per_day) return defer("rate_limit_campaign_day");
  if (sentWithin(snap, ws, HOUR, now) >= wsHourlyCap()) return defer("rate_limit_workspace_hour");

  // render from the authorized plan now; a stored adaptation is used only if it still validates
  const r = renderMessage(c.plan, a, it.step, "email");
  if (r.errors.length) return cancel(`render_failed: ${r.errors.join("; ").slice(0, 200)}`);
  let subject = r.subject, body = r.body;
  if (it.adapted && it.plan_hash === c.authorization.plan_hash && !validateAdaptation(r.core, it.adapted.body, r.claims_used, c.plan).length) {
    subject = it.adapted.subject; body = withFooter(it.adapted.body, c.plan, "email");
  }
  const checks = validateMessage({ subject, body, from_email: c.plan.sender.email, from_name: c.plan.sender.name }, c.plan, "email");
  if (!passes(checks)) {
    const why = checks.filter((x) => !x.ok).map((x) => x.name).join(", ");
    await writeItem(deps, { ...it, status: "failed", reason: `invalid_message: ${why}` });
    return out("failed", `invalid_message: ${why}`);
  }

  const sending: OutboxItem = { ...it, status: "sending", subject, body, attempts: it.attempts + 1, transport: deps.transport.name, reason: "" };
  await writeItem(deps, sending);
  const res = await deps.transport.send({
    ws, campaign_id: c.id, account_id: a.id, outbox_id: it.id, idem_key: it.idem_key, step: it.step, to: a.email,
    from_email: c.plan.sender.email, from_name: c.plan.sender.name, subject, body, attachments: c.plan.attachments,
    headers: { "X-Idempotency-Key": it.idem_key, "X-Campaign": c.id },
  }).catch((e) => ({ ok: false as const, code: "network", message: String(e).slice(0, 200) }));

  if (res.ok) {
    await writeItem(deps, { ...sending, status: "sent", sent_at: iso(now), provider_id: res.provider_id });
    await logEvent(deps, ws, c.id, "sent", { account_id: a.id, to: a.email, linkedin_url: a.linkedin_url, outbox_id: it.id, idem_key: it.idem_key, step: it.step, subject, body_hash: sha(body).slice(0, 16), claims_used: r.claims_used, transport: deps.transport.name, provider_id: res.provider_id });
    if (it.step === 0) await engineMove(deps, a, "contacted", `first message ${iso(now).slice(0, 10)}`, "system");
    if (it.step < c.plan.follow_up_limit) {
      const gap = c.plan.cadence.gap_days[it.step] ?? 7;
      await enqueue(deps, ws, { campaign_id: c.id, account_id: a.id, step: it.step + 1, due_at: iso(now + gap * DAY) }, "system").catch(() => null);
    }
    return out("sent", res.provider_id);
  }

  const cls = classifySendError(res.code);
  if (cls === "hard_bounce") {
    await writeItem(deps, { ...sending, status: "failed", reason: "hard_bounce", last_error: `${res.code} ${res.message}`.slice(0, 300) });
    await addSuppression(deps, ws, a.email, "hard_bounce", `send ${res.code}`, "system");
    await closeAccount(deps, a, `hard bounce ${res.code}`);
    await logEvent(deps, ws, c.id, "bounce", { account_id: a.id, to: a.email, code: res.code, outbox_id: it.id });
    await cancelQueued(deps, await deps.store.load(), ws, (d) => String(d.to || "").toLowerCase() === a.email.toLowerCase(), "hard_bounce", "system");
    await autoStop(deps, ws, c.id);
    return out("failed", `hard_bounce ${res.code}`);
  }
  if (cls === "sender") {
    await writeItem(deps, { ...sending, status: "queued", attempts: it.attempts, reason: "sender_error", last_error: `${res.code} ${res.message}`.slice(0, 300) });
    await pauseCampaign(deps, ws, c.id, "system", `sender_error ${res.code}`);
    return out("deferred", `sender_error ${res.code}: campaign paused`);
  }
  if (cls === "permanent" || sending.attempts >= MAX_ATTEMPTS) {
    await writeItem(deps, { ...sending, status: "failed", reason: cls === "permanent" ? "permanent_error" : "retries_exhausted", last_error: `${res.code} ${res.message}`.slice(0, 300) });
    await logEvent(deps, ws, c.id, "send_failed", { account_id: a.id, code: res.code, outbox_id: it.id, class: cls });
    return out("failed", `${cls} ${res.code}`);
  }
  const backoff = 15 * 60e3 * 2 ** (sending.attempts - 1);
  await writeItem(deps, { ...sending, status: "queued", due_at: iso(now + backoff), reason: "transient_retry", last_error: `${res.code} ${res.message}`.slice(0, 300) });
  await logEvent(deps, ws, c.id, "send_retry", { account_id: a.id, code: res.code, outbox_id: it.id, attempt: sending.attempts });
  return out("retry", `transient ${res.code}`);
}

// Processes due items (oldest first), re-reading the store before each one so replies, campaign status,
// suppression and the kill switch are rechecked immediately before every send and follow-up.
export async function tick(deps: Deps, opts: { enabled?: boolean; limit?: number; ws?: string } = {}): Promise<{ enabled: boolean; results: TickResult[]; error?: string }> {
  const enabled = opts.enabled ?? process.env.OUTREACH_ENABLED === "1";
  if (!enabled) return { enabled: false, results: [] };
  if (deps.transport.live && process.env.OUTREACH_LIVE_TRANSPORT !== "1") return { enabled: true, results: [], error: "a live transport is not allowed in this build" };
  const limit = Math.max(1, Math.min(50, opts.limit ?? 10));
  const results: TickResult[] = [];
  const tried = new Set<string>();
  const wsFilter = opts.ws ? asWs(opts.ws) : "";

  // a send that never returned is not retried automatically: a human checks it (the provider may have sent it)
  const first = await deps.store.load();
  for (const w of new Set(first.outbox.map((r) => asWs(r.ws)))) {
    if (wsFilter && w !== wsFilter) continue;
    for (const it of outboxItems(first, w)) {
      if (it.status === "sending" && deps.now() - Date.parse(latest(first.outbox, w).get(it.id)!.time) > STUCK_SENDING_MS) {
        await writeItem(deps, { ...it, status: "needs_review", reason: "send did not complete; check the provider before retrying" });
        results.push({ id: it.id, ws: w, action: "needs_review", reason: "stuck in sending" });
      }
    }
  }

  // a deferral that applies to a whole campaign or workspace skips the rest of it for this tick (fewer store reads)
  const blockedCampaign = /^(campaign_|not_authorized|scope_changed|sender_|rate_limit_campaign)/;
  const skip = new Set<string>();
  for (let i = 0; i < limit; i++) {
    const snap = await deps.store.load();
    const nowIso = iso(deps.now());
    let next: OutboxItem | null = null;
    for (const w of new Set(snap.outbox.map((r) => asWs(r.ws)))) {
      if ((wsFilter && w !== wsFilter) || skip.has(w)) continue;
      for (const it of outboxItems(snap, w)) {
        if (it.status !== "queued" || it.due_at > nowIso || tried.has(`${w}|${it.id}`) || skip.has(`${w}|${it.campaign_id}`)) continue;
        if (!next || it.due_at < next.due_at) next = it;
      }
    }
    if (!next) break;
    tried.add(`${next.ws}|${next.id}`);
    const r = await processItem(deps, snap, next);
    results.push(r);
    if (r.action === "deferred") {
      if (r.reason === "emergency_stop" || r.reason === "rate_limit_workspace_hour") skip.add(next.ws);
      else if (blockedCampaign.test(r.reason)) skip.add(`${next.ws}|${next.campaign_id}`);
    }
  }
  return { enabled: true, results };
}

// ---------------- replies ----------------

// Reply classification hook: records the reply, applies its effect (suppress, stage, stop follow-ups) and flags
// replies that need a human. Replies are untrusted data; only the category is acted on.
export async function handleReply(deps: Deps, ws: string, req: { campaign_id: string; account_id: string; text: string; subject?: string; channel?: "email" | "linkedin"; category?: ReplyCategory }, by: string) {
  ws = asWs(ws);
  const snap = await deps.store.load();
  const c = readCampaign(snap, ws, req.campaign_id);
  if (!c) throw new Error("campaign not found");
  const a = readAccounts(snap, ws, c.id).find((x) => x.id === req.account_id);
  if (!a) throw new Error("account not found");
  const cls = req.category ? { category: req.category, by: "human" as const } : await classifyReply(String(req.text || ""), String(req.subject || ""), deps.classifyModel);
  const eff = replyEffect(cls.category);
  await logEvent(deps, ws, c.id, "reply", { account_id: a.id, category: cls.category, classified_by: cls.by, channel: req.channel || "email", excerpt: String(req.text || "").slice(0, 500), to: a.email }, by);
  if (eff.suppress && a.email) await addSuppression(deps, ws, a.email, cls.category, `reply in ${c.id}`, by);
  if (eff.stage) await engineMove(deps, a, eff.stage, `reply: ${cls.category}`, by);
  let cancelled = 0;
  if (eff.stop) {
    const fresh = await deps.store.load();
    cancelled = await cancelQueued(deps, fresh, ws, (d) => (d.campaign_id === c.id && d.account_id === a.id) || (eff.suppress && !!a.email && String(d.to || "").toLowerCase() === a.email.toLowerCase()), `reply_${cls.category}`, by);
  }
  if (eff.human) await logEvent(deps, ws, c.id, "needs_human", { account_id: a.id, category: cls.category }, by);
  if (cls.category === "hard_bounce" || cls.category === "opt_out") await autoStop(deps, ws, c.id);
  return { category: cls.category, classified_by: cls.by, effect: eff, cancelled };
}

// ---------------- preview ----------------

export async function previewMessage(deps: Deps, ws: string, campaignId: string, accountId: string, step = 0, adapt = false) {
  ws = asWs(ws);
  const snap = await deps.store.load();
  const c = readCampaign(snap, ws, campaignId);
  if (!c) throw new Error("campaign not found");
  const a = readAccounts(snap, ws, c.id).find((x) => x.id === accountId);
  if (!a) throw new Error("account not found");
  const r = renderMessage(c.plan, a, step, c.plan.channel);
  const checks = validateMessage({ subject: r.subject, body: r.body, from_email: c.plan.sender.email, from_name: c.plan.sender.name }, c.plan, c.plan.channel);
  const ident = c.plan.channel === "email" ? await deps.transport.verifySender(ws, c.plan.sender.email) : null;
  checks.push({ name: "verified_sender", ok: c.plan.channel !== "email" || ident === c.plan.sender.name, detail: ident ? `verified as ${ident}` : "no verified sender connection" });
  const sup = isSuppressed(snap, ws, a.email, c.id);
  checks.push({ name: "not_suppressed", ok: !sup, detail: sup ? `suppressed: ${sup.reason}` : "not on the suppression list" });
  checks.push({ name: "render", ok: !r.errors.length, detail: r.errors.join("; ") || "all fields filled" });
  let adapted: { subject: string; body: string } | null = null, adapt_rejected: string[] = [];
  if (adapt && c.plan.channel === "email" && deps.adaptModel && !r.errors.length) {
    const x = await adaptWording(c.plan, a, step, deps.adaptModel);
    adapted = x.adapted ? { subject: x.adapted.subject, body: withFooter(x.adapted.body, c.plan, "email") } : null;
    adapt_rejected = x.rejected;
  }
  const scope = scopeSummary(snap, ws, c);
  return {
    to: c.plan.channel === "email" ? a.email : a.linkedin_url, from: { name: c.plan.sender.name, email: c.plan.sender.email, org: c.plan.sender.org },
    subject: r.subject, body: r.body, attachments: c.plan.attachments, template_id: r.template_id,
    claims_used: c.plan.claims.filter((x) => r.claims_used.includes(x.id)),
    checks, ok: passes(checks), adapted, adapt_rejected, scope_hash: scope.scope_hash, needs_reauthorization: scope.needs_reauthorization,
  };
}
