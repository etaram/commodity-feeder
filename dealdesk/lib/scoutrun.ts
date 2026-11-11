// One round of the scouts (app/api/cron/scout calls it): load the fresh signals through the same data the agent's
// tools read (search_winners: the winners index; search_tenders: the tender store), let lib/scout.ts choose, record
// every decision in the tab 'Scout Seen', and start a deal agent run for each chosen signal. The run reports to the
// owner in Telegram and every outgoing message still waits for his Approve button (lib/dealagent.ts, lib/sendguard.ts):
// a scout starts research, it never sends anything.
//
// Off unless SCOUT=on. Limits (environment, with defaults):
//   SCOUT_MAX_RUNS_PER_DAY 3     runs started per UTC day
//   SCOUT_MAX_RUNS_PER_ROUND 1   runs started by one call, so the owner gets one lead at a time
//   SCOUT_MAX_TURNS 12           model calls per run (the normal agent limit is AGENT_MAX_TURNS, 24)
//   SCOUT_MAX_USD_PER_RUN 1      a run ends once its estimated cost reaches this
//   SCOUT_HOURS_UTC 5-15         hours of the day (UTC) in which rounds start runs; "0-23" for always
//   SCOUT_WINNER_DAYS 21         an award older than this is not fresh
//   SCOUT_MIN_DAYS_LEFT 10       a tender closing sooner is skipped
//   SCOUT_MIN_SCORE 40           a signal scoring less is not worth a run
//   SCOUT_FOCUS                  focus words, comma separated, used when the workspace strategy holds none
// The daily AI budget (AI_DAILY_BUDGET_USD, lib/anthropic.ts) is respected: a run starts only when today's estimated
// spend plus the run's own cost limit still fits under it.
import { DEFAULT_WS } from "@/lib/auth";
import { appendRow, ENGINE_SHEET, readRanges } from "@/lib/sheets";
import { cellsToSeen, choose, LIMIT, NO_FOCUS, PURSUED, pursuedOn, SCOUT_SEEN, seenToCells, START_FAILED, winnerSignalId, ageDays,
  type Focus, type Limits, type Pick, type SeenRow, type Signal } from "@/lib/scout";
import type { Winner } from "@/lib/index";

const envNum = (k: string, d: number, min = 0) => { const n = Number(process.env[k]); return process.env[k] !== undefined && process.env[k] !== "" && Number.isFinite(n) && n >= min ? n : d; };
export const scoutOn = () => (process.env.SCOUT || "").trim().toLowerCase() === "on";
export function scoutConfig() {
  const m = (process.env.SCOUT_HOURS_UTC || "5-15").match(/^\s*(\d{1,2})\s*-\s*(\d{1,2})\s*$/);
  const from = m ? Math.min(23, Number(m[1])) : 5, to = m ? Math.min(23, Number(m[2])) : 15;
  return { maxRunsPerDay: Math.floor(envNum("SCOUT_MAX_RUNS_PER_DAY", 3)), maxRunsPerRound: Math.floor(envNum("SCOUT_MAX_RUNS_PER_ROUND", 1, 1)), maxTurns: Math.floor(envNum("SCOUT_MAX_TURNS", 12, 3)),
    maxUsd: envNum("SCOUT_MAX_USD_PER_RUN", 1, 0.05), winnerDays: envNum("SCOUT_WINNER_DAYS", 21, 1), minDaysLeft: envNum("SCOUT_MIN_DAYS_LEFT", 10), minScore: envNum("SCOUT_MIN_SCORE", 40),
    hours: [from, to] as [number, number], focusWords: (process.env.SCOUT_FOCUS || "").split(",").map((x) => x.trim().slice(0, 60)).filter(Boolean).slice(0, 30) };
}
export type ScoutConfig = ReturnType<typeof scoutConfig>;

// ---- signals from the data ---------------------------------------------------------------------------------
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/,/g, "")); return Number.isFinite(n) ? n : null; };
export function winnerSignal(w: Winner): Signal {
  return { kind: "winner", id: winnerSignalId(w), title: w.t || "", country: w.c || "", buyer: w.b || "", value_usd: Number(w.v) || 0, link: w.l || "", source: w.s || "",
    date: w.d || "", winner: (w.w || []).join("; "), winner_country: w.wc || "", winner_kind: w.k || "", needs: w.n || [], commodity: w.cm || "",
    website: w.ws || "", contact: [...(w.ce || []), ...(w.cp || [])].join(", "), contact_page: w.cs || "", buyer_awards: null };
}
/** A row of the tender store; only a row the index marks new (first seen in the last 2 days) is a signal. */
export function tenderSignal(r: Record<string, string>): Signal | null {
  if (!r.id || !String(r.new || "").trim() || String(r.stage || "").toLowerCase() === "planned") return null;
  return { kind: "tender", id: r.id, title: r.title_en || r.title_original || "", country: r.country || "", buyer: r.buyer || "", value_usd: num(r.est_value_usd) || 0, link: r.link || "", source: r.source || "",
    days_left: num(r.days_left), fit: num(r.fit || r.score), sector: r.sector || "", access: r.access || "", decision: r.decision || "", commodity: r.commodity || "", nature: r.nature || "", buyer_awards: num(r.buyer_awards_12m) };
}

// ---- dependencies ------------------------------------------------------------------------------------------
export type Owner = { chat: string; email: string; name: string; lang: "he" | "en"; ws: string };
export type StartArgs = { chat: string; email: string; name: string; lang: "he" | "en"; ws: string; request: string; origin: string; max_turns: number; max_usd: number };
export type ScoutDeps = {
  now: () => number;
  owner: () => Promise<Owner | null>;
  winners: () => Promise<Winner[]>;
  tenders: () => Promise<Record<string, string>[]>;
  /** awards the award data holds for a buyer, or null when it has no record */
  buyerAwards: (buyer: string, country: string) => Promise<number | null>;
  focus: (ws: string) => Promise<Focus>;
  /** today's estimated AI spend and the daily line; alert_usd 0 = no line set */
  budget: () => Promise<{ spent_usd: number; alert_usd: number }>;
  seen: () => Promise<SeenRow[]>;
  record: (row: SeenRow) => Promise<void>;
  start: (o: StartArgs) => Promise<{ id: string; deal_id: string }>;
  notify: (owner: Owner, pick: Pick, runId: string) => Promise<void>;
  /** one round at a time: false when another round holds the claim */
  claim: () => Promise<{ ok: boolean; release: () => Promise<void> }>;
};

export async function readSeen(): Promise<SeenRow[]> {
  const g = (await readRanges(ENGINE_SHEET, [`'${SCOUT_SEEN}'!A2:K50000`]).catch((e) => { if (String(e).includes("Unable to parse range")) return null; throw e; }))?.[0] || [];
  return g.map(cellsToSeen).filter((r): r is SeenRow => !!r);
}

const esc = (s: unknown) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
/** The short note the owner gets when a scout opens a lead, before the run's own reports arrive. */
export function scoutNote(p: Pick, he: boolean): string {
  const kind = p.signal.kind === "winner" ? (he ? "זוכה טרי בחוזה" : "fresh contract winner") : (he ? "מכרז חדש" : "new tender");
  return he
    ? `<b>סקאוט פתח ליד</b> (${kind}, ציון ${p.score})\n${esc(p.label)}\nמוביל/ה: ${esc(p.assignee.name)}, ${esc(p.assignee.he)}\nלמה נבחר: ${esc(p.reasons.slice(0, 5).join("; "))}\nהסוכן בודק עכשיו ויחזור עם סיכום. שום דבר לא יוצא החוצה בלי האישור שלך.`
    : `<b>A scout opened a lead</b> (${kind}, score ${p.score})\n${esc(p.label)}\nLead: ${esc(p.assignee.name)}, ${esc(p.assignee.title)}\nWhy: ${esc(p.reasons.slice(0, 5).join("; "))}\nThe agent is checking it now and will report. Nothing goes out without your approval.`;
}

export async function liveDeps(): Promise<ScoutDeps> {
  const [{ winners }, { allTenders }, { buyerProfile }, { getStrategy }, { budgetState }, tg, { startRun }, { claim }, { workspaceOf }] = await Promise.all([
    import("@/lib/index"), import("@/lib/panel"), import("@/lib/index"), import("@/lib/strategy"), import("@/lib/anthropic"), import("@/lib/telegram"), import("@/lib/dealagent"), import("@/lib/claims"), import("@/lib/users")]);
  return {
    now: () => Date.now(),
    // the owner: a linked Telegram chat of an active admin of the original workspace (the same test as the Approve button)
    owner: async () => {
      for (const l of await tg.links(true)) {
        if (l.alerts === "off" || !(await tg.isOwner(l.email))) continue;
        const ws = await workspaceOf(l.email).catch(() => DEFAULT_WS);
        if (ws === DEFAULT_WS) return { chat: l.chat_id, email: l.email, name: l.name, lang: l.lang, ws };
      }
      return null;
    },
    winners: async () => { const w = await winners(); if (w.error) throw new Error(`winners index: ${w.error}`); return w.rows; },
    tenders: async () => (await allTenders()).rows as Record<string, string>[],
    buyerAwards: async (buyer, country) => { const p = await buyerProfile(buyer, country, 1); return p.rows[0] ? p.rows[0].a : null; },
    focus: async (ws) => { const st = await getStrategy(ws).catch(() => null); return st ? { words: st.focus, partners: st.partners, excluded: st.excluded } : NO_FOCUS; },
    budget: async () => budgetState(),
    seen: readSeen,
    record: async (row) => { await appendRow(SCOUT_SEEN, seenToCells(row)); },
    start: async (o) => { const r = await startRun(tg.agentIo, o); return { id: r.id, deal_id: r.deal_id }; },
    notify: async (owner, pick) => { await tg.send(owner.chat, scoutNote(pick, owner.lang === "he")); },
    claim: () => claim("scout:round", 5 * 60_000),
  };
}

export type RoundResult = { ok: boolean; scout: "on" | "off"; started: number; skipped: number; looked: number; note: string; runs: string[] };
const none = (note: string, scout: "on" | "off" = "on"): RoundResult => ({ ok: true, scout, started: 0, skipped: 0, looked: 0, note, runs: [] });

/** One round. dry: decide and report, record nothing and start nothing. */
export async function scoutRound(d: ScoutDeps, o: { dry?: boolean } = {}): Promise<RoundResult> {
  if (!scoutOn()) return none("SCOUT is not on", "off");
  const cfg = scoutConfig(), now = d.now(), day = new Date(now).toISOString().slice(0, 10), hour = new Date(now).getUTCHours();
  if (hour < cfg.hours[0] || hour > cfg.hours[1]) return none(`outside the scout hours (${cfg.hours[0]}-${cfg.hours[1]} UTC)`);
  const owner = await d.owner();
  if (!owner) return none("no owner with a linked Telegram chat: nobody to report to, so nothing is started");
  const lock = o.dry ? { ok: true, release: async () => {} } : await d.claim();
  if (!lock.ok) return none("another round is running");
  try {
    const seen = await d.seen();
    const runsToday = pursuedOn(seen, owner.ws, day);
    const b = await d.budget();
    const budgetRuns = b.alert_usd > 0 ? Math.max(0, Math.floor((b.alert_usd - b.spent_usd) / cfg.maxUsd)) : Infinity;
    const heldToday = seen.some((r) => r.ws === owner.ws && r.decision === LIMIT && r.time.startsWith(day));
    // the day's limit is used up and that is already on record: nothing to load, nothing to write
    if (!o.dry && (runsToday >= cfg.maxRunsPerDay || budgetRuns <= 0) && heldToday) return none(runsToday >= cfg.maxRunsPerDay ? "daily run limit reached" : "no room left in today's AI budget");

    const [ws, ts, st] = await Promise.all([d.winners(), d.tenders(), d.focus(owner.ws)]);
    const focus: Focus = { ...st, words: st.words.length ? st.words : cfg.focusWords };
    const cand: Signal[] = [
      ...ws.filter((w) => { const a = ageDays(w.d, now); return Number.isFinite(a) && a <= cfg.winnerDays; }).map(winnerSignal),
      ...ts.map(tenderSignal).filter((s): s is Signal => !!s)];
    const lim: Limits = { maxRunsPerDay: cfg.maxRunsPerDay, runsToday, maxRunsPerRound: cfg.maxRunsPerRound, budgetRuns, minScore: cfg.minScore, look: 12, maxTurns: cfg.maxTurns, winnerDays: cfg.winnerDays, minDaysLeft: cfg.minDaysLeft };
    // first pass without the buyers' records, then the record of the few winners that may be chosen, then the real choice
    const first = choose(cand, seen, owner.ws, focus, { ...lim, look: 8, maxRunsPerRound: 8, maxRunsPerDay: runsToday + 8, budgetRuns: 8 }, now);
    for (const p of first.chosen) if (p.signal.kind === "winner" && p.signal.buyer) p.signal.buyer_awards = await d.buyerAwards(p.signal.buyer, p.signal.country).catch(() => null);
    const res = choose(cand, seen, owner.ws, focus, lim, now);
    if (o.dry) return { ok: true, scout: "on", started: 0, skipped: res.skipped.length, looked: res.chosen.length + res.skipped.length, runs: [],
      note: `dry run: would start ${res.chosen.length} (${res.chosen.map((p) => `${p.signal.kind} ${p.score}`).join(", ") || "none"})${res.held_by ? `; held: ${res.held_by}` : ""}` };

    const row = (p: Pick, decision: string, run_id = "", deal_id = "", extra: string[] = []): SeenRow => ({ time: new Date(d.now()).toISOString(), ws: owner.ws, kind: p.signal.kind, id: p.signal.id, score: p.score, decision, run_id,
      assignees: [p.assignee.id, ...p.support.map((m) => m.id)], label: p.label, reasons: [...extra, ...p.reasons], deal_id });
    const last = new Map(seen.filter((r) => r.ws === owner.ws).map((r) => [`${r.kind}:${r.id}`, r]));
    let skipped = 0, final = 0;
    for (const p of res.skipped) {
      // signals turned down for good are recorded a few a round (the next round looks at the next ones), so the tab stays small
      if (p.decision !== LIMIT && ++final > 6) continue;
      // a signal held back by a limit is written once a day, not once a round
      const prev = last.get(`${p.signal.kind}:${p.signal.id}`);
      if (p.decision === LIMIT && prev?.decision === LIMIT && prev.time.startsWith(day)) continue;
      await d.record(row(p, p.decision)); skipped++;
    }
    const runs: string[] = [];
    for (const p of res.chosen) {
      // on record as pursued before the run exists: a round that dies here cannot start the same signal twice
      await d.record(row(p, PURSUED));
      try {
        const r = await d.start({ chat: owner.chat, email: owner.email, name: owner.name, lang: owner.lang, ws: owner.ws, request: p.brief, origin: "scout", max_turns: cfg.maxTurns, max_usd: cfg.maxUsd });
        await d.record(row(p, PURSUED, r.id, r.deal_id));
        runs.push(r.id);
        await d.notify(owner, p, r.id).catch(() => {});
      } catch (e) {
        await d.record(row(p, START_FAILED, "", "", [`the run could not be started: ${String((e as Error).message || e).slice(0, 160)}`])).catch(() => {});
      }
    }
    return { ok: true, scout: "on", started: runs.length, skipped, looked: res.chosen.length + res.skipped.length, runs, note: res.held_by || (cand.length ? "" : "no fresh signals in the data") };
  } finally { await lock.release(); }
}
