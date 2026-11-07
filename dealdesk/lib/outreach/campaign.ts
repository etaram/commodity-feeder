import { asWs } from "@/lib/auth";
import { forbiddenHits, passes, renderMessage, validateMessage } from "./draft";
import { canonical, latest, nextRev, sha, TABS, type Row, type Snapshot, type Store, type TabKey } from "./store";
import { isSuppressed } from "./suppression";
import type { Transport } from "./transport";
import type { Account, AccountStage, Authorization, Campaign, CampaignPlan, CampaignStatus, Channel, Template } from "./types";

export type Ctx = { store: Store; now: () => number };
export const iso = (ms: number) => new Date(ms).toISOString();
export const CONTROL_ID = "__control__"; // per-workspace emergency stop row in the Campaigns tab

// ---------------- state machines ----------------

export const CAMPAIGN_NEXT: Record<CampaignStatus, CampaignStatus[]> = {
  draft: ["authorized", "cancelled"],
  authorized: ["running", "paused", "cancelled", "stopped"],
  running: ["paused", "cancelled", "stopped"],
  paused: ["running", "cancelled", "stopped"],
  stopped: ["authorized", "cancelled"], // a stopped campaign needs a fresh authorization before it can run again
  cancelled: [],
};
export const canMoveCampaign = (from: CampaignStatus, to: CampaignStatus) => CAMPAIGN_NEXT[from]?.includes(to) ?? false;

export const STAGES: AccountStage[] = ["identified", "reviewed", "campaign_eligible", "contact_confirmed", "outreach_authorized", "contacted", "response_classified", "qualified", "nurture", "closed"];
export const STAGE_NEXT: Record<AccountStage, AccountStage[]> = {
  identified: ["reviewed", "closed"],
  reviewed: ["campaign_eligible", "closed"],
  campaign_eligible: ["contact_confirmed", "closed"],
  contact_confirmed: ["outreach_authorized", "closed"],
  outreach_authorized: ["contacted", "closed"],
  contacted: ["response_classified", "closed"],
  response_classified: ["qualified", "nurture", "closed"],
  qualified: ["closed"],
  nurture: ["qualified", "closed"],
  closed: [],
};
// Set only by the engine: authorization, a send (or a logged manual LinkedIn contact) and reply classification.
export const SYSTEM_STAGES: AccountStage[] = ["outreach_authorized", "contacted", "response_classified"];
export const canMoveStage = (from: AccountStage, to: AccountStage) => STAGE_NEXT[from]?.includes(to) ?? false;

// ---------------- plan normalisation, validation and scope ----------------

const str = (v: unknown, n = 500) => String(v ?? "").replace(/\r/g, "").trim().slice(0, n);
const list = (v: unknown, n = 40, m = 300) => (Array.isArray(v) ? v : []).map((x) => str(x, m)).filter(Boolean).slice(0, n);
const num = (v: unknown, d: number, lo: number, hi: number) => { const x = Number(v); return Number.isFinite(x) ? Math.min(hi, Math.max(lo, Math.round(x))) : d; };
const ident = (v: unknown) => str(v, 40).toLowerCase().replace(/[^a-z0-9_-]/g, "");

export const DEFAULT_OPT_OUT = "If you would rather not hear from us, reply \"unsubscribe\" and we will not contact you again.";
export const DEFAULT_LI_OPT_OUT = "Not relevant? Tell me and I will not follow up.";

export function normalizePlan(input: unknown): CampaignPlan {
  const p = (input && typeof input === "object" ? input : {}) as Record<string, any>;
  const s = (p.sender || {}) as Record<string, unknown>;
  const v = (p.volume || {}) as Record<string, unknown>;
  const a = (p.auto_stop || {}) as Record<string, unknown>;
  const channel: Channel = p.channel === "linkedin" ? "linkedin" : "email";
  const templates: Template[] = (Array.isArray(p.templates) ? p.templates : []).slice(0, 20).map((t: any, i: number) => ({
    id: ident(t?.id) || `t${i + 1}`,
    step: num(t?.step, 0, 0, 5),
    channel: t?.channel === "linkedin" ? "linkedin" : "email",
    kind: t?.kind === "connect" || t?.kind === "message" ? t.kind : t?.channel === "linkedin" ? "message" : "email",
    subject: str(t?.subject, 160),
    body: str(t?.body, 6000),
  }));
  return {
    name: str(p.name, 120), client: str(p.client, 120), segment: str(p.segment, 200), objective: str(p.objective, 1000),
    target_profile: str(p.target_profile, 2000), exclusions: list(p.exclusions),
    owner: str(p.owner, 120),
    sender: { name: str(s.name, 80), email: str(s.email, 120).toLowerCase(), org: str(s.org, 120), title: str(s.title, 80), address: str(s.address, 200) },
    channel,
    claims: (Array.isArray(p.claims) ? p.claims : []).slice(0, 30).map((c: any, i: number) => ({ id: ident(c?.id) || `c${i + 1}`, text: str(c?.text, 400), source: str(c?.source, 400) })).filter((c: { text: string }) => c.text),
    offer: str(p.offer, 600),
    attachments: (Array.isArray(p.attachments) ? p.attachments : []).slice(0, 5).map((x: any) => ({ name: str(x?.name, 120), ref: str(x?.ref, 400) })).filter((x: { name: string }) => x.name),
    templates,
    personalization_fields: list(p.personalization_fields, 12, 40).map(ident).filter(Boolean),
    cadence: { gap_days: (Array.isArray(p.cadence?.gap_days) ? p.cadence.gap_days : [4, 7]).slice(0, 5).map((d: unknown) => num(d, 5, 1, 60)) },
    follow_up_limit: num(p.follow_up_limit, 1, 0, 3),
    volume: { per_hour: num(v.per_hour, 5, 1, 30), per_day: num(v.per_day, 20, 1, 200), max_accounts: num(v.max_accounts, 20, 1, 200), budget: str(v.budget, 200) },
    research_tasks: list(p.research_tasks), review_dates: list(p.review_dates, 12, 20), stop_conditions: list(p.stop_conditions), success_metrics: list(p.success_metrics),
    auto_stop: { max_hard_bounces: num(a.max_hard_bounces, 3, 1, 50), max_opt_outs: num(a.max_opt_outs, 5, 1, 50) },
    recent_contact_days: num(p.recent_contact_days, 30, 0, 365),
    opt_out_line: str(p.opt_out_line, 300) || DEFAULT_OPT_OUT,
    linkedin_opt_out_line: str(p.linkedin_opt_out_line, 80) || DEFAULT_LI_OPT_OUT,
    adapt_wording: p.adapt_wording === true,
    pilot_review_note: str(p.pilot_review_note, 1000),
  };
}

const EMAIL_RE = /^[^\s@<>"',;]+@[^\s@<>"',;]+\.[a-z]{2,}$/i;
export const validEmail = (e: string) => EMAIL_RE.test(e) && e.length <= 120;

// Problems that block authorization (a draft may be saved with them).
export function validatePlan(p: CampaignPlan): string[] {
  const e: string[] = [];
  if (!p.name) e.push("name is required");
  if (!p.objective) e.push("objective is required");
  if (!p.target_profile) e.push("target profile is required");
  if (!p.owner) e.push("owner is required");
  if (!p.sender.name || !p.sender.org || !validEmail(p.sender.email)) e.push("sender name, organisation and a valid email are required");
  if (!p.claims.length) e.push("at least one approved claim is required");
  for (const c of p.claims) {
    if (!c.source) e.push(`claim ${c.id} has no source (every claim must be traceable)`);
    const h = forbiddenHits(c.text);
    if (h.length) e.push(`claim ${c.id} contains ${h.join(", ")}`);
  }
  if (new Set(p.claims.map((c) => c.id)).size !== p.claims.length) e.push("claim ids must be unique");
  const ho = forbiddenHits(p.offer);
  if (ho.length) e.push(`offer contains ${ho.join(", ")}`);
  const tpl = p.templates.filter((t) => t.channel === p.channel);
  for (let step = 0; step <= (p.channel === "email" ? p.follow_up_limit : 0); step++) {
    if (!tpl.some((t) => t.step === step)) e.push(`a ${p.channel} template for step ${step} is required`);
  }
  if (p.channel === "email" && p.cadence.gap_days.length < p.follow_up_limit) e.push("cadence needs a gap (days) for every follow-up");
  for (const t of p.templates) {
    const h = forbiddenHits(`${t.subject}\n${t.body}`.replace(/\{\{[^}]*\}\}/g, " "));
    if (h.length) e.push(`template ${t.id} contains ${h.join(", ")}`);
    if (t.channel === "email" && !t.subject) e.push(`template ${t.id} needs a subject`);
  }
  if (new Set(p.templates.map((t) => t.id)).size !== p.templates.length) e.push("template ids must be unique");
  if (!p.success_metrics.length) e.push("at least one success metric is required");
  if (!p.stop_conditions.length) e.push("stop conditions are required");
  if (!p.review_dates.length) e.push("at least one review date is required");
  return e;
}

// The material scope an authorization covers. Changing any of these requires a new authorization.
const SCOPE_FIELDS: (keyof CampaignPlan)[] = ["target_profile", "exclusions", "sender", "channel", "claims", "offer", "attachments", "templates", "personalization_fields", "cadence", "follow_up_limit", "volume", "auto_stop", "recent_contact_days", "opt_out_line", "linkedin_opt_out_line", "adapt_wording"];
export function planHash(p: CampaignPlan): string {
  const o: Record<string, unknown> = {};
  for (const k of SCOPE_FIELDS) o[k] = p[k];
  return sha(canonical(o));
}
export const audienceKey = (a: Account) => `${a.id}|${a.email.toLowerCase()}|${a.linkedin_url}`;
export function scopeHash(p: CampaignPlan, audience: string[]): string {
  return sha(canonical({ plan: planHash(p), audience: [...audience].sort() }));
}

// ---------------- reading ----------------

export function readCampaign(snap: Snapshot, ws: string, id: string): Campaign | null {
  if (id.startsWith("__")) return null;
  const r = latest(snap.campaigns, ws).get(id);
  return r ? (r.data as unknown as Campaign) : null;
}
export function listCampaigns(snap: Snapshot, ws: string): Campaign[] {
  return [...latest(snap.campaigns, ws).values()].filter((r) => !r.id.startsWith("__")).map((r) => r.data as unknown as Campaign)
    .sort((a, b) => b.updated_at.localeCompare(a.updated_at));
}
export function readAccounts(snap: Snapshot, ws: string, campaignId?: string): Account[] {
  return [...latest(snap.accounts, ws).values()].map((r) => r.data as unknown as Account).filter((a) => !campaignId || a.campaign_id === campaignId);
}
export function killSwitch(snap: Snapshot, ws: string): { engaged: boolean; by: string; at: string; reason: string } {
  const r = latest(snap.campaigns, ws).get(CONTROL_ID);
  const d = (r?.data || {}) as Record<string, string>;
  return { engaged: r?.status === "engaged", by: d.by || "", at: d.at || "", reason: d.reason || "" };
}

// The audience an authorization would cover now: accounts past contact confirmation, not closed, not suppressed.
export function currentAudience(snap: Snapshot, ws: string, c: Campaign): Account[] {
  const confirmedRank = STAGES.indexOf("contact_confirmed");
  return readAccounts(snap, ws, c.id).filter((a) => STAGES.indexOf(a.stage) >= confirmedRank && a.stage !== "closed"
    && !isSuppressed(snap, ws, a.email, c.id) && (c.plan.channel === "linkedin" ? !!a.linkedin_url : validEmail(a.email)));
}

export function needsReauthorization(c: Campaign): boolean {
  return !c.authorization || c.authorization.plan_hash !== planHash(c.plan);
}

// ---------------- writing ----------------

export async function put(ctx: Ctx, tab: TabKey, r: { ws: string; campaign_id: string; id: string; status: string; data: object; by: string }) {
  const row: Row = { time: iso(ctx.now()), ws: asWs(r.ws), campaign_id: r.campaign_id, id: r.id, rev: nextRev(ctx.now()), status: r.status, data: r.data as Record<string, unknown>, by: r.by };
  await ctx.store.append(tab, row);
  return row;
}

export async function logEvent(ctx: Ctx, ws: string, campaignId: string, kind: string, data: Record<string, unknown>, by = "system") {
  const id = `EV-${sha(`${ws}|${campaignId}|${kind}|${ctx.now()}|${Math.random()}`).slice(0, 16)}`;
  return put(ctx, "log", { ws, campaign_id: campaignId, id, status: kind, data: { kind, at: iso(ctx.now()), ...data }, by });
}

export async function writeCampaign(ctx: Ctx, c: Campaign, by: string) {
  c.updated_at = iso(ctx.now());
  await put(ctx, "campaigns", { ws: c.ws, campaign_id: c.id, id: c.id, status: c.status, data: c, by });
}

/** A move made by the engine (a send, a reply, a logged LinkedIn contact). It follows STAGE_NEXT; when the target is
 *  two steps away through response_classified (a reply that books a meeting), both steps are written. A move the
 *  table does not allow is skipped and logged, so the engine never pulls an account backwards or out of closed. */
export async function engineMove(ctx: Ctx, a: Account, to: AccountStage, reason: string, by: string): Promise<Account> {
  if (a.stage === to) return a;
  const path: AccountStage[] = canMoveStage(a.stage, to) ? [to]
    : canMoveStage(a.stage, "response_classified") && canMoveStage("response_classified", to) ? ["response_classified", to] : [];
  if (!path.length) {
    await logEvent(ctx, a.ws, a.campaign_id, "stage_skipped", { account_id: a.id, from: a.stage, to, reason: str(reason, 200) }, by);
    return a;
  }
  let cur = a;
  for (const st of path) {
    const next = { ...cur, stage: st, stage_reason: str(reason, 300) };
    await writeAccount(ctx, next, by);
    await logEvent(ctx, a.ws, a.campaign_id, "stage", { account_id: a.id, from: cur.stage, to: st, reason: next.stage_reason }, by);
    cur = next;
  }
  return cur;
}

export async function writeAccount(ctx: Ctx, a: Account, by: string) {
  a.updated_at = iso(ctx.now());
  await put(ctx, "accounts", { ws: a.ws, campaign_id: a.campaign_id, id: a.id, status: a.stage, data: a, by });
}

export async function saveCampaign(ctx: Ctx, ws: string, input: { id?: string; plan: unknown }, by: string): Promise<{ campaign: Campaign; errors: string[]; needs_reauthorization: boolean }> {
  ws = asWs(ws);
  const snap = await ctx.store.load();
  const plan = normalizePlan(input.plan);
  let c = input.id ? readCampaign(snap, ws, String(input.id)) : null;
  if (input.id && !c) throw new Error("campaign not found");
  if (c && c.status === "cancelled") throw new Error("a cancelled campaign cannot be changed");
  if (!c) {
    const id = `CMP-${sha(`${ws}|${by}|${ctx.now()}|${Math.random()}`).slice(0, 10).toUpperCase()}`;
    c = { id, ws, status: "draft", status_reason: "", plan, authorization: null, created_by: by, created_at: iso(ctx.now()), updated_at: "" };
  } else c = { ...c, plan };
  await writeCampaign(ctx, c, by);
  const reauth = c.status !== "draft" && needsReauthorization(c);
  if (reauth) await logEvent(ctx, ws, c.id, "scope_changed", { note: "material scope changed; sending is blocked until re-authorized" }, by);
  return { campaign: c, errors: validatePlan(plan), needs_reauthorization: reauth };
}

const exclusionHit = (p: CampaignPlan, a: Account) => {
  const hay = `${a.company} ${a.country} ${a.title} ${a.notes} ${a.email}`.toLowerCase();
  return p.exclusions.find((x) => x && hay.includes(x.toLowerCase())) || "";
};

export async function upsertAccounts(ctx: Ctx, ws: string, campaignId: string, input: unknown[], by: string): Promise<{ added: number; updated: number; accounts: Account[] }> {
  ws = asWs(ws);
  const snap = await ctx.store.load();
  const c = readCampaign(snap, ws, campaignId);
  if (!c) throw new Error("campaign not found");
  if (c.status === "cancelled") throw new Error("campaign is cancelled");
  const existing = new Map(readAccounts(snap, ws, campaignId).map((a) => [a.id, a]));
  let added = 0, updated = 0;
  const out: Account[] = [];
  for (const raw of input.slice(0, 200)) {
    const x = (raw || {}) as Record<string, any>;
    const email = str(x.email, 120).toLowerCase();
    const company = str(x.company, 160);
    if (!company) continue;
    const id = str(x.id, 40) || `AC-${sha(`${ws}|${campaignId}|${email || company.toLowerCase()}|${str(x.contact_name, 80).toLowerCase()}`).slice(0, 12)}`;
    const prev = existing.get(id);
    const fields: Record<string, string> = {};
    for (const [k, v] of Object.entries(x.fields && typeof x.fields === "object" ? x.fields : {}).slice(0, 20)) fields[ident(k)] = str(v, 200);
    const a: Account = {
      id, ws, campaign_id: campaignId, stage: prev?.stage || "identified", stage_reason: prev?.stage_reason || "",
      company, contact_name: str(x.contact_name, 80), first_name: str(x.first_name, 40), last_name: str(x.last_name, 40), title: str(x.title, 80),
      email, linkedin_url: str(x.linkedin_url, 200), country: str(x.country, 60), contact_source: str(x.contact_source, 300),
      conflict: x.conflict === true, fields, notes: str(x.notes, 1000), updated_at: "",
    };
    // a confirmed contact whose address changes drops back to review: the new address has not been confirmed
    if (prev && STAGES.indexOf(prev.stage) >= STAGES.indexOf("contact_confirmed") && (prev.email !== a.email || prev.linkedin_url !== a.linkedin_url) && prev.stage !== "closed") {
      a.stage = "campaign_eligible"; a.stage_reason = "contact detail changed; confirm again";
    }
    await writeAccount(ctx, a, by);
    prev ? updated++ : added++;
    out.push(a);
  }
  return { added, updated, accounts: out };
}

// A human moves an account one stage (or closes it). Requirements are checked in code.
export async function moveStage(ctx: Ctx, ws: string, campaignId: string, accountId: string, to: AccountStage, reason: string, by: string): Promise<Account> {
  ws = asWs(ws);
  const snap = await ctx.store.load();
  const c = readCampaign(snap, ws, campaignId);
  if (!c) throw new Error("campaign not found");
  const a = readAccounts(snap, ws, campaignId).find((x) => x.id === accountId);
  if (!a) throw new Error("account not found");
  if (!STAGES.includes(to)) throw new Error("unknown stage");
  if (SYSTEM_STAGES.includes(to)) throw new Error(`${to} is set by the engine, not by hand`);
  if (!canMoveStage(a.stage, to)) throw new Error(`cannot move from ${a.stage} to ${to}`);
  if (to === "campaign_eligible") {
    const hit = exclusionHit(c.plan, a);
    if (hit) throw new Error(`account matches exclusion "${hit}"`);
    if (a.conflict) throw new Error("account is flagged as a conflict");
  }
  if (to === "contact_confirmed") {
    if (!a.contact_source) throw new Error("contact_source is required (where the contact detail came from)");
    if (c.plan.channel === "email" && !validEmail(a.email)) throw new Error("a valid email is required");
    if (c.plan.channel === "linkedin" && !a.linkedin_url) throw new Error("a LinkedIn profile URL is required");
    if (a.email && isSuppressed(snap, ws, a.email, campaignId)) throw new Error("this address is on the suppression list");
  }
  const next = { ...a, stage: to, stage_reason: str(reason, 300) };
  await writeAccount(ctx, next, by);
  await logEvent(ctx, ws, campaignId, "stage", { account_id: a.id, from: a.stage, to, reason: next.stage_reason }, by);
  return next;
}

// Cancels queued outbox items matching a filter (stop conditions, cancellation). Returns the count.
export async function cancelQueued(ctx: Ctx, snap: Snapshot, ws: string, match: (d: Record<string, any>) => boolean, reason: string, by: string): Promise<number> {
  let n = 0;
  for (const r of latest(snap.outbox, ws).values()) {
    if (r.status !== "queued" || !match(r.data)) continue;
    await put(ctx, "outbox", { ws, campaign_id: r.campaign_id, id: r.id, status: "cancelled", data: { ...r.data, status: "cancelled", reason }, by });
    n++;
  }
  return n;
}

// ---------------- authorization ----------------

export function audienceCap(p: CampaignPlan) { return Math.min(p.volume.max_accounts, p.pilot_review_note ? 200 : 20); }

// What an admin is about to authorize; the UI shows this and sends back scope_hash as confirm_scope_hash.
export function scopeSummary(snap: Snapshot, ws: string, c: Campaign) {
  const aud = currentAudience(snap, ws, c);
  const keys = aud.map(audienceKey);
  return {
    scope_hash: scopeHash(c.plan, keys), plan_hash: planHash(c.plan), audience_size: aud.length, audience_cap: audienceCap(c.plan),
    audience: aud.map((a) => ({ id: a.id, company: a.company, contact_name: a.contact_name, email: a.email, stage: a.stage })),
    channel: c.plan.channel, sender: c.plan.sender, claims: c.plan.claims, offer: c.plan.offer, templates: c.plan.templates,
    personalization_fields: c.plan.personalization_fields, cadence: c.plan.cadence, follow_up_limit: c.plan.follow_up_limit, volume: c.plan.volume,
    authorized: c.authorization, needs_reauthorization: c.status !== "draft" && needsReauthorization(c), errors: validatePlan(c.plan),
  };
}

export async function authorizeCampaign(ctx: Ctx, transport: Transport, ws: string, campaignId: string, confirmScopeHash: string, by: string): Promise<{ ok: true; authorization: Authorization } | { ok: false; errors: string[] }> {
  ws = asWs(ws);
  const snap = await ctx.store.load();
  const c = readCampaign(snap, ws, campaignId);
  if (!c) return { ok: false, errors: ["campaign not found"] };
  if (c.status === "cancelled") return { ok: false, errors: ["campaign is cancelled"] };
  const errors = validatePlan(c.plan);
  const ident = await transport.verifySender(ws, c.plan.sender.email);
  if (c.plan.channel === "email") {
    if (ident === null) errors.push("the sender mailbox has no verified sender connection");
    else if (ident !== c.plan.sender.name) errors.push(`the verified sender is "${ident}", not "${c.plan.sender.name}" (no impersonation)`);
  }
  const aud = currentAudience(snap, ws, c);
  if (!aud.length) errors.push("no accounts with a confirmed contact");
  if (aud.length > audienceCap(c.plan)) errors.push(`audience of ${aud.length} exceeds the cap of ${audienceCap(c.plan)} (start with a reviewed pilot of 10-20; a pilot review note raises the cap)`);
  for (const a of aud) {
    for (const t of c.plan.templates.filter((x) => x.channel === c.plan.channel)) {
      const r = renderMessage(c.plan, a, t.step, t.channel, t.kind);
      if (r.errors.length) { errors.push(`${a.company}, template ${t.id}: ${r.errors.join("; ")}`); continue; }
      const checks = validateMessage({ subject: r.subject, body: r.body, from_email: c.plan.sender.email, from_name: c.plan.sender.name }, c.plan, t.channel);
      for (const ch of checks) if (!ch.ok) errors.push(`${a.company}, template ${t.id}: ${ch.name} (${ch.detail})`);
    }
  }
  const keys = aud.map(audienceKey);
  const hash = scopeHash(c.plan, keys);
  if (!confirmScopeHash || confirmScopeHash !== hash) errors.push("the scope changed since it was reviewed: reload the preview and confirm the current scope hash");
  if (errors.length) return { ok: false, errors: errors.slice(0, 40) };
  const authorization: Authorization = { by, at: iso(ctx.now()), scope_hash: hash, plan_hash: planHash(c.plan), audience: keys };
  const next: Campaign = { ...c, authorization, status: c.status === "draft" || c.status === "stopped" ? "authorized" : c.status, status_reason: "authorized" };
  await writeCampaign(ctx, next, by);
  for (const a of aud) if (a.stage === "contact_confirmed") await engineMove(ctx, a, "outreach_authorized", `authorized by ${by}`, by);
  await logEvent(ctx, ws, c.id, "authorize", { scope_hash: hash, plan_hash: authorization.plan_hash, audience_size: keys.length }, by);
  return { ok: true, authorization };
}

export const TAB_NAMES = TABS;
