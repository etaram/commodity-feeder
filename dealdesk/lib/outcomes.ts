// Outcome ledger (acceptance test F11 "Historical learning"). Pure module: no clock, no network, no sheet access.
// It records what verifiably happened to a case, with proof, from now on. It does not score, rank, predict or train.
// There are no first-party closed deals in the system today; nothing here creates one.

export const FUNNEL = ["signal_found", "need_confirmed", "technical_match", "rfq_authorized", "rfq_sent", "rfq_responded", "quote_received",
  "proposal_delivered", "negotiation_advanced", "contract_signed", "delivered_invoiced", "cash_collected"] as const;
export const TERMINAL = ["lost", "abandoned"] as const;
export const EVENT_TYPES = [...FUNNEL, ...TERMINAL] as const;
export const REASONS = ["right_product", "wrong_spec", "already_purchased", "timing", "no_contact", "uncompetitive_price", "logistics", "financing",
  "regulatory", "poor_signal", "not_interested", "other"] as const;
export const RIGHTS = ["own", "client_confidential", "public"] as const;
export const PROOF_KINDS = ["source", "message", "document"] as const;

export type FunnelStage = (typeof FUNNEL)[number];
export type EventType = (typeof EVENT_TYPES)[number];
export type Reason = (typeof REASONS)[number];
export type RightsScope = (typeof RIGHTS)[number];
export type Proof = { kind: (typeof PROOF_KINDS)[number]; id: string };
export type OutcomeEvent = {
  type: EventType; case_id: string; route_id: string; workspace: string;
  at: string;                 // ISO time the event happened (not the time it was typed in)
  actor: string;              // who did or recorded it
  counterparty: string;       // "" when the stage has none yet (a signal with no named buyer)
  proof: Proof;               // required: source id, message id or document id
  rights_scope: RightsScope;
  model_version: string;      // the model or rule set that produced the suggestion; "none" for a purely manual event
  display_rank: number | null; // position the case was shown at when the user acted; null when it was not shown in a list
  reason: Reason | null;      // required for lost / abandoned, null otherwise
};
export type CaseLabel = FunnelStage | "lost" | "abandoned" | "pending" | "no_response_censored" | "not_contacted";
export type CaseStatus = {
  case_id: string | null;
  stage: FunnelStage | null;  // furthest verified positive stage, whatever the label
  label: CaseLabel;
  known_negative: boolean;    // true only for a recorded lost event
  censored: boolean;          // the outcome is unknown: not contacted, still pending, or no reply in the window
  reason: Reason | null;
  as_of: string;
  ignored: string[];          // events left out of the reading, with the cause
};

const DAY = 86_400_000;
const WS_RE = /^[a-z0-9][a-z0-9-]{1,39}$/;
/** Stages that only our own (or a client's) action can reach. A public notice is never proof of one of them. */
const FIRST_PARTY = new Set<EventType>(["rfq_authorized", "rfq_sent", "rfq_responded", "quote_received", "proposal_delivered", "negotiation_advanced",
  "contract_signed", "delivered_invoiced", "cash_collected", "lost", "abandoned"]);

export function timeMs(iso: unknown, what = "time"): number {
  const s = typeof iso === "string" ? iso : "";
  const t = /^\d{4}-\d{2}-\d{2}/.test(s) ? Date.parse(s) : NaN;
  if (Number.isNaN(t)) throw new Error(`${what} is not a readable ISO time: ${JSON.stringify(iso)}`);
  return t;
}
const str = (v: unknown) => typeof v === "string" && v.trim().length > 0;

/** Every reason an event cannot enter the ledger; an empty list means it is acceptable. */
export function eventProblems(e: Partial<OutcomeEvent> | null | undefined): string[] {
  const p: string[] = [];
  if (!e || typeof e !== "object") return ["not an event"];
  if (!EVENT_TYPES.includes(e.type as EventType)) p.push(`unknown event type ${JSON.stringify(e.type)}`);
  for (const k of ["case_id", "route_id", "actor", "model_version"] as const) if (!str(e[k])) p.push(`${k} is required`);
  if (typeof e.counterparty !== "string") p.push("counterparty must be a string (empty when there is none yet)");
  if (!WS_RE.test(String(e.workspace ?? ""))) p.push("workspace is missing or not a valid workspace id");
  try { timeMs(e.at, "at"); } catch (x) { p.push((x as Error).message); }
  if (!e.proof || !PROOF_KINDS.includes(e.proof.kind) || !str(e.proof.id)) p.push("proof is required: a source id, message id or document id");
  if (!RIGHTS.includes(e.rights_scope as RightsScope)) p.push(`unknown rights_scope ${JSON.stringify(e.rights_scope)}`);
  if (e.display_rank !== null && !(Number.isInteger(e.display_rank) && (e.display_rank as number) >= 1)) p.push("display_rank must be null or a whole number from 1");
  const terminal = (TERMINAL as readonly string[]).includes(String(e.type));
  if (terminal && !REASONS.includes(e.reason as Reason)) p.push(`${e.type} needs a reason from the fixed list`);
  if (!terminal && e.reason != null) p.push("reason is only for lost / abandoned");
  if (e.rights_scope === "public" && FIRST_PARTY.has(e.type as EventType)) p.push(`${e.type} cannot be recorded from public information: a public award or notice is not our own outcome`);
  return p;
}

/** Point-in-time view: only what had happened by asOf. */
export function snapshot<T extends { at: string }>(caseEvents: T[], asOf: string): T[] {
  const lim = timeMs(asOf, "asOf");
  return caseEvents.filter((e) => { try { return timeMs(e.at, "at") <= lim; } catch { return false; } });
}

export type Feature = { name: string; observed_at: string; value?: unknown };
/** Throws when any feature was observed after asOf, or carries no readable observation time (then nothing proves it is earlier). */
export function assertNoLeakage(features: Feature[], asOf: string): void {
  const lim = timeMs(asOf, "asOf");
  const bad: string[] = [];
  for (const f of features) {
    let t: number;
    try { t = timeMs(f.observed_at, "observed_at"); } catch { bad.push(`${f.name} (no readable observed_at)`); continue; }
    if (t > lim) bad.push(`${f.name} (observed ${f.observed_at})`);
  }
  if (bad.length) throw new Error(`leakage: ${bad.length} feature(s) are not known as of ${asOf}: ${bad.join("; ")}`);
}

/** Furthest verified stage and an honest label for one case, read as of `now`. The caller supplies the clock. */
export function caseStatus(events: OutcomeEvent[], now: string, followUpDays: number): CaseStatus {
  const nowMs = timeMs(now, "now");
  if (!(typeof followUpDays === "number" && followUpDays > 0 && Number.isFinite(followUpDays))) throw new Error("followUpDays must be a positive number");
  const ids = new Set(events.map((e) => e?.case_id));
  if (ids.size > 1) throw new Error("caseStatus reads one case at a time; these events belong to several cases");
  const ignored: string[] = [];
  const good: (OutcomeEvent & { t: number })[] = [];
  for (const e of events) {
    const probs = eventProblems(e);
    if (probs.length) { ignored.push(`${String(e?.type)}: ${probs[0]}`); continue; }
    const t = timeMs(e.at);
    if (t > nowMs) continue;   // not yet happened at this point in time: silently outside the view
    good.push({ ...e, t });
  }
  good.sort((a, b) => a.t - b.t);
  const idx = (e: OutcomeEvent) => FUNNEL.indexOf(e.type as FunnelStage);
  const positive = good.filter((e) => idx(e) >= 0);
  const top = positive.reduce<(typeof good)[number] | null>((m, e) => (!m || idx(e) > idx(m) ? e : m), null);
  const stage = top ? (top.type as FunnelStage) : null;
  const base = { case_id: events[0]?.case_id ?? null, stage, as_of: now, ignored };
  // a terminal event stands unless a later positive event reopened the case
  const end = [...good].reverse().find((e) => idx(e) < 0);
  if (end && !positive.some((e) => e.t > end.t)) {
    return { ...base, label: end.type as "lost" | "abandoned", known_negative: end.type === "lost", censored: false, reason: end.reason };
  }
  const sentIdx = FUNNEL.indexOf("rfq_sent");
  if (!top || idx(top) < sentIdx) return { ...base, label: "not_contacted", known_negative: false, censored: true, reason: null };
  if (idx(top) > sentIdx) return { ...base, label: stage as FunnelStage, known_negative: false, censored: false, reason: null };
  const lastSent = Math.max(...positive.filter((e) => e.type === "rfq_sent").map((e) => e.t));
  const waiting = nowMs - lastSent <= followUpDays * DAY;
  return { ...base, label: waiting ? "pending" : "no_response_censored", known_negative: false, censored: true, reason: null };
}

// ---- store and ledger ----------------------------------------------------------------------------------------------

/** Append-only storage. The production store is not built in this task; tests use the in-memory one. */
export interface OutcomeStore { append(e: OutcomeEvent): Promise<void>; all(): Promise<OutcomeEvent[]> }
export function memoryStore(): OutcomeStore {
  const rows: OutcomeEvent[] = [];
  return { async append(e) { rows.push(e); }, async all() { return rows.map((r) => ({ ...r, proof: { ...r.proof } })); } };
}
const wsOrThrow = (ws: string) => { if (!WS_RE.test(String(ws ?? ""))) throw new Error("a valid workspace id is required"); return ws; };
const sameEvent = (a: OutcomeEvent, b: OutcomeEvent) => a.workspace === b.workspace && a.case_id === b.case_id && a.route_id === b.route_id && a.type === b.type
  && a.at === b.at && a.proof.kind === b.proof.kind && a.proof.id === b.proof.id;

export function createLedger(store: OutcomeStore) {
  return {
    /** Adds one event. Rejects (throws) an event without proof or with any other problem; an exact repeat is not stored twice. */
    async record(e: OutcomeEvent): Promise<{ stored: boolean }> {
      const probs = eventProblems(e);
      if (probs.length) throw new Error(`outcome event rejected: ${probs.join("; ")}`);
      if ((await store.all()).some((x) => sameEvent(x, e))) return { stored: false };
      await store.append({ type: e.type, case_id: e.case_id, route_id: e.route_id, workspace: e.workspace, at: e.at, actor: e.actor, counterparty: e.counterparty,
        proof: { kind: e.proof.kind, id: e.proof.id }, rights_scope: e.rights_scope, model_version: e.model_version, display_rank: e.display_rank, reason: e.reason ?? null });
      return { stored: true };
    },
    /** What a workspace may see: all of its own events, and nothing of another workspace except events marked public. */
    async list(workspace: string): Promise<OutcomeEvent[]> {
      const ws = wsOrThrow(workspace);
      return (await store.all()).filter((e) => e.workspace === ws || e.rights_scope === "public");
    },
    /** One case inside one workspace. A case id guessed from another workspace returns nothing. */
    async caseEvents(workspace: string, case_id: string): Promise<OutcomeEvent[]> {
      const ws = wsOrThrow(workspace);
      return (await store.all()).filter((e) => e.workspace === ws && e.case_id === case_id);
    },
    /** Rows a workspace may learn from: its own events marked own or public, plus public events of others. Never client_confidential. */
    async exportForLearning(workspace: string): Promise<OutcomeEvent[]> {
      const ws = wsOrThrow(workspace);
      return (await store.all()).filter((e) => e.rights_scope === "public" || (e.workspace === ws && e.rights_scope === "own"));
    },
    /** Rows that may be pooled across workspaces: public only. Own events stay with their workspace; client_confidential never leaves. */
    async pooledExport(): Promise<OutcomeEvent[]> {
      return (await store.all()).filter((e) => e.rights_scope === "public");
    },
  };
}
