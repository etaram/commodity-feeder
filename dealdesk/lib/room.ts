// The operations room (app/room): what the agent team is doing, shaped from rows the system already stores. Pure: the
// API route (app/api/room) reads the tabs and passes the raw rows in; nothing here reads, writes or calls a model.
// Every line on the screen comes from a stored row: a member with no row behind them is shown idle, a counter with no
// source says so, and nothing is made up to look busy.
//
// Sources: 'Agent Runs' (A id, B time, C chat, D email, E status, F turns, G run JSON; one row per saved step),
// 'Agent Approvals' (A id, B run id, C chat, D time, E status, F message JSON; one row per state), 'Scout Seen'
// (lib/scout.ts), 'Send Guard' (A time, B ws, C key, D status; lib/sendguard.ts) and the missions of the workspace.
//
// Who is doing what: one model run plays every role, and the stored run does not say which member is "speaking". A
// member is tied to a run by what the run did: the tool it used last (TOOL_ROLE), the member who signed a proposed
// message (from_role), and the members a scout assigned. That is an attribution by rule, and the screen says so.
import { TEAM, member, type Member } from "@/lib/team";
import { personasFor, type Mission } from "@/lib/mission";
import { cellsToSeen, PURSUED, type SeenRow } from "@/lib/scout";

const DAY = 864e5;
/** A run still marked running whose last saved step is older than this did not chain its next step. */
export const STALE_MS = 15 * 60_000;
const cut = (v: unknown, n: number) => { const s = String(v ?? "").replace(/\s+/g, " ").trim(); return s.length > n ? s.slice(0, n - 1) + "…" : s; };
const ilDay = (t: number) => new Date(t).toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 10);
const ms = (iso: string) => { const t = Date.parse(iso); return Number.isFinite(t) ? t : 0; };

// The role that owns each tool of the deal agent (lib/dealagent.ts TOOLS, lib/team.ts "does"). record, report,
// ask_owner and finish belong to whoever is working, so they map to nobody.
export const TOOL_ROLE: Record<string, string> = { search_tenders: "analyst", tender_routes: "analyst", search_winners: "analyst", company_footprint: "analyst", buyer_profile: "analyst",
  search_suppliers: "sourcing", supplier_contact: "sourcing", deal_economics: "economics", compare_quotes: "negotiation", logistics_options: "logistics" };

/** One line, in Hebrew with the data as it is stored, for a tool call. */
export function describeTool(name: string, x: Record<string, unknown> = {}): string {
  const s = (k: string, n = 80) => cut(x[k], n);
  switch (name) {
    case "search_suppliers": return `חיפוש ספקים במאגר: ${s("product")}${s("origin_country") ? ` (${s("origin_country")})` : ""}`;
    case "supplier_contact": return `פרטי קשר של ספק מהמאגר: ${s("company")}`;
    case "search_tenders": return `חיפוש מכרזים פתוחים: ${s("words")}${s("country") ? ` (${s("country")})` : ""}`;
    case "search_winners": return `חיפוש זוכים טריים בחוזים: ${s("words") || s("country") || "כל המאגר"}`;
    case "company_footprint": return `רקורד חוזים ציבוריים של חברה: ${s("company")}`;
    case "buyer_profile": return `פרופיל קונה ציבורי: ${s("buyer")}`;
    case "tender_routes": return `דרכי כניסה למכרז ${s("tender_id", 40)}`;
    case "deal_economics": return "חישוב כלכלת העסקה (תרחיש)";
    case "record": return `שמירה בתיק העסקה: ${({ requirement: "דרישה", party: "צד לעסקה", quote: "הצעת מחיר" } as Record<string, string>)[s("kind", 20)] || s("kind", 20)}`;
    case "compare_quotes": return "השוואת הצעות מחיר על בסיס אחד";
    case "propose_message": return `הכנת פנייה לאישור הבעלים: ${s("to_name")}`;
    case "logistics_options": return `אפשרויות לוגיסטיקה ליעד ${s("destination_country", 10)}`;
    case "ask_owner": return `שאלה לבעלים: ${s("question", 140)}`;
    case "report": return `דיווח ביניים לבעלים: ${s("text", 140)}`;
    case "finish": return `סיכום: ${s("summary", 220)}`;
    default: return `כלי: ${cut(name, 40)}`;
  }
}

// ---- reading the stored rows -------------------------------------------------------------------------------
type Block = { type?: string; id?: string; name?: string; input?: Record<string, unknown> };
type RunJson = { id?: string; ws?: string; status?: string; request?: string; deal_id?: string; turns?: number; usd?: number; started?: string; note?: string; origin?: string; msgs?: { role?: string; content?: unknown }[] };
export type ToolUse = { at: string; name: string; input: Record<string, unknown> };
export type RunView = { id: string; ws: string; status: string; title: string; deal_id: string; origin: string; started: string; updated: string; turns: number; usd: number; note: string; summary: string; tools: ToolUse[] };

/** Runs from the raw rows. A tool call gets the time of the first saved step it appears in: steps are saved every few
 *  model turns, so the time is that of the step, not of the call itself. */
export function readRuns(rows: string[][]): RunView[] {
  const by = new Map<string, { time: string; j: RunJson }[]>();
  for (const r of rows) {
    if (!r?.[0] || !r[6]) continue;
    try { const j = JSON.parse(r[6]) as RunJson; by.set(r[0], [...(by.get(r[0]) || []), { time: r[1] || "", j }]); } catch { /* a cut row */ }
  }
  const out: RunView[] = [];
  for (const [id, steps] of by) {
    const last = steps[steps.length - 1], seen = new Set<string>(), tools: ToolUse[] = [];
    let summary = "";
    for (const st of steps) for (const m of st.j.msgs || []) {
      if (m.role !== "assistant" || !Array.isArray(m.content)) continue;
      for (const b of m.content as Block[]) {
        if (b?.type !== "tool_use" || !b.id || seen.has(b.id)) continue;
        seen.add(b.id);
        tools.push({ at: st.time, name: String(b.name || ""), input: (b.input && typeof b.input === "object" ? b.input : {}) as Record<string, unknown> });
        if (b.name === "finish") summary = cut(b.input?.summary, 400);
      }
    }
    out.push({ id, ws: String(last.j.ws || ""), status: String(last.j.status || ""), title: cut(String(last.j.request || "").split("\n")[0], 160), deal_id: String(last.j.deal_id || ""), origin: String(last.j.origin || ""),
      started: String(last.j.started || steps[0].time), updated: last.time, turns: Number(last.j.turns) || 0, usd: Number(last.j.usd) || 0, note: cut(last.j.note, 200), summary, tools });
  }
  return out;
}

export type ApprovalView = { id: string; run_id: string; status: string; created: string; updated: string; decided: string; approved: boolean; to_name: string; subject: string; why: string; from_role: string; unverified: boolean };
/** States a message reaches only after the owner pressed Approve (lib/dealagent.ts decide). */
const AFTER_APPROVE = new Set(["sending", "sent", "send_failed", "delivery_unknown", "needs_review", "blocked"]);
export function readApprovals(rows: string[][]): ApprovalView[] {
  const by = new Map<string, string[][]>();
  for (const r of rows) if (r?.[0]) by.set(r[0], [...(by.get(r[0]) || []), r]);
  return [...by.entries()].map(([id, rs]) => {
    let m: Record<string, unknown> = {};
    try { m = JSON.parse(rs[0][5] || "{}"); } catch { /* unreadable message */ }
    const first = rs.find((r) => AFTER_APPROVE.has(r[4]) || r[4] === "rejected"), last = rs[rs.length - 1];
    return { id, run_id: rs[0][1] || "", status: last[4] || "", created: rs[0][3] || "", updated: last[3] || "", decided: first?.[3] || "", approved: !!first && first[4] !== "rejected",
      to_name: cut(m.to_name, 80), subject: cut(m.subject, 140), why: cut(m.why, 200), from_role: String(m.from_role || ""), unverified: !!m.unverified };
  });
}

// ---- the view ----------------------------------------------------------------------------------------------
export type MemberState = "working" | "waiting" | "stalled" | "done_today" | "idle";
export type MemberView = { id: string; name: string; title: string; he: string; region: string; state: MemberState; now: string; since: string; deal_id: string; last_active: string; today: number };
export type FeedItem = { at: string; kind: "start" | "tool" | "proposed" | "approved" | "rejected" | "sent" | "send_problem" | "question" | "finish" | "stopped" | "error" | "scout"; text: string; who: string; run_id: string; deal_id: string };
export type HuntItem = { at: string; kind: string; label: string; score: number; decision: string; reasons: string[]; assignees: string[]; run_id: string; deal_id: string };
export type PendingView = { id: string; status: string; at: string; to_name: string; subject: string; why: string; by: string; unverified: boolean; deal_id: string; run_title: string };
export type RoomView = {
  at: string; day: string; scout_on: boolean;
  team: MemberView[]; feed: FeedItem[];
  hunt: { looked: number; pursued: number; skipped: { reason: string; n: number }[]; items: HuntItem[] };
  waiting: PendingView[];
  counters: { days: number; runs: number; scout_runs: number; proposed: number; approved: number; rejected: number; sent: number; replies: null; replies_note: string; est_usd: number };
  running: number; notes: string[];
};
export type RoomInput = { ws: string; now: number; runs: string[][]; approvals: string[][]; seen: string[][]; guard: string[][]; missions: Mission[]; scoutOn: boolean; errors?: string[] };

const REGION: Record<string, string> = { analyst: "כל האזורים", sourcing: "כל האזורים", relations_asia: "מזרח ודרום-מזרח אסיה", relations_south_asia: "דרום אסיה", relations_latam: "אמריקה הלטינית", relations_africa: "אפריקה",
  relations_europe: "אירופה ומרכז אסיה", relations_mena: "המזרח התיכון וצפון אפריקה", negotiation: "כל האזורים", logistics: "כל האזורים", economics: "כל האזורים", evidence: "כל האזורים" };
const who = (id: string) => member(id)?.name || "";
const hhmm = (iso: string) => (ms(iso) ? new Date(ms(iso)).toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(11, 16) : "");

export function shapeRoom(i: RoomInput): RoomView {
  const today = ilDay(i.now), weekAgo = i.now - 7 * DAY;
  const runs = readRuns(i.runs).filter((r) => r.ws === i.ws);
  const runById = new Map(runs.map((r) => [r.id, r]));
  const approvals = readApprovals(i.approvals).filter((a) => runById.has(a.run_id));
  const seenAll = i.seen.map(cellsToSeen).filter((r): r is SeenRow => !!r && r.ws === i.ws);
  // the scout's assignment of a run: the members it named when it started the run
  const scoutOf = new Map<string, SeenRow>();
  for (const s of seenAll) if (s.run_id) scoutOf.set(s.run_id, s);
  const live = (r: RunView) => r.status === "running" && i.now - ms(r.updated) < STALE_MS;
  const stalled = (r: RunView) => r.status === "running" && !live(r);

  // ---- team
  type Slot = { state: MemberState; now: string; since: string; deal_id: string; rank: number };
  const RANK: Record<MemberState, number> = { working: 4, waiting: 3, stalled: 2, done_today: 1, idle: 0 };
  const slot = new Map<string, Slot>(), lastActive = new Map<string, string>(), todayN = new Map<string, number>();
  const put = (id: string, state: MemberState, now: string, since: string, deal_id: string) => {
    if (!member(id)) return;
    const cur = slot.get(id);
    if (!cur || RANK[state] > cur.rank || (RANK[state] === cur.rank && since > cur.since)) slot.set(id, { state, now, since, deal_id, rank: RANK[state] });
  };
  const touch = (id: string, at: string) => {
    if (!member(id) || !at) return;
    if (at > (lastActive.get(id) || "")) lastActive.set(id, at);
    if (ilDay(ms(at)) === today) todayN.set(id, (todayN.get(id) || 0) + 1);
  };
  for (const r of runs) {
    const sc = scoutOf.get(r.id), lead = sc?.assignees[0] || "";
    const roleOf = (t: ToolUse) => (t.name === "propose_message" ? String(t.input.from_role || "") : TOOL_ROLE[t.name] || "");
    for (const t of r.tools) touch(roleOf(t), t.at);
    for (const a of sc?.assignees || []) touch(a, sc!.time);
    const lastRoled = [...r.tools].reverse().find((t) => roleOf(t) && member(roleOf(t)));
    const involved = new Set([...r.tools.map(roleOf), ...(sc?.assignees || [])].filter((x) => member(x)));
    if (live(r)) {
      if (lastRoled) put(roleOf(lastRoled), "working", describeTool(lastRoled.name, lastRoled.input), lastRoled.at, r.deal_id);
      if (lead && (!lastRoled || roleOf(lastRoled) !== lead)) put(lead, "working", `מוביל/ה ליד של סקאוט: ${cut(sc!.label, 120)}`, sc!.time, r.deal_id);
      if (!lastRoled && !lead && r.tools.length === 0) { /* a run that has not used a tool yet belongs to nobody in particular */ }
    } else if (r.status === "waiting") {
      const q = [...r.tools].reverse().find((t) => t.name === "ask_owner");
      const id = lead || (lastRoled ? roleOf(lastRoled) : "");
      if (id) put(id, "waiting", `מחכה לתשובת הבעלים: ${cut(q?.input.question, 140) || "שאלה פתוחה"}`, r.updated, r.deal_id);
    } else if (stalled(r)) {
      for (const id of lead ? [lead] : lastRoled ? [roleOf(lastRoled)] : []) put(id, "stalled", `הריצה לא התקדמה מאז ${hhmm(r.updated)} (אין צעד שמור חדש): ${r.title}`, r.updated, r.deal_id);
    } else if (r.status === "done" && ilDay(ms(r.updated)) === today) {
      for (const id of involved) put(id, "done_today", `סיים/ה היום: ${r.title}`, r.updated, r.deal_id);
    }
  }
  for (const a of approvals) {
    touch(a.from_role, a.created);
    if (a.status === "pending" || a.status === "needs_review" || a.status === "delivery_unknown")
      put(a.from_role, "waiting", `${a.status === "pending" ? "פנייה ממתינה לאישור הבעלים" : "פנייה ממתינה לבדיקת הבעלים"}: ${a.to_name}`, a.updated, runById.get(a.run_id)?.deal_id || "");
  }
  // missions: a task names a role; it is tied to a member only when the role has exactly one persona
  for (const m of i.missions) for (const t of m.tasks) {
    const p = personasFor(t.role);
    if (p.length !== 1 || (t.status !== "running" && t.status !== "queued")) continue;
    if (t.status === "running") put(p[0].id, "working", `משימה (${m.id}): ${cut(t.question, 140)}`, m.updated_at, m.deal_id);
    else if (m.status === "queued" || m.status === "running") put(p[0].id, "waiting", `משימה בתור (${m.id}): ${cut(t.question, 140)}`, m.updated_at, m.deal_id);
  }
  const team: MemberView[] = TEAM.map((m: Member) => {
    const s = slot.get(m.id);
    return { id: m.id, name: m.name, title: m.title, he: m.he, region: REGION[m.id] || "", state: s?.state || "idle", now: s?.now || "", since: s?.since || "", deal_id: s?.deal_id || "", last_active: lastActive.get(m.id) || "", today: todayN.get(m.id) || 0 };
  });

  // ---- feed
  const feed: FeedItem[] = [];
  for (const r of runs) {
    const sc = scoutOf.get(r.id), base = { run_id: r.id, deal_id: r.deal_id };
    feed.push({ at: r.started, kind: "start", text: `${r.origin === "scout" || sc ? "סקאוט פתח ריצה" : "ריצה התחילה"}: ${r.title}`, who: who(sc?.assignees[0] || ""), ...base });
    for (const t of r.tools) {
      if (t.name === "propose_message") continue;   // shown from the approvals tab, with its real time and state
      const kind = t.name === "finish" ? "finish" : t.name === "ask_owner" ? "question" : "tool";
      feed.push({ at: t.at, kind, text: t.name === "finish" ? `ריצה הסתיימה. ${describeTool(t.name, t.input)}` : describeTool(t.name, t.input), who: who(TOOL_ROLE[t.name] || ""), ...base });
    }
    if (r.status === "error") feed.push({ at: r.updated, kind: "error", text: `הריצה נעצרה בתקלה: ${r.note || "ללא פירוט"}`, who: "", ...base });
    if (r.status === "stopped") feed.push({ at: r.updated, kind: "stopped", text: `הריצה נעצרה בידי הבעלים: ${r.title}`, who: "", ...base });
    if (r.status === "done" && !r.summary) feed.push({ at: r.updated, kind: "finish", text: `ריצה הסתיימה ללא סיכום מסודר${r.note ? ` (${r.note})` : ""}: ${r.title}`, who: "", ...base });
  }
  const PROBLEM: Record<string, string> = { send_failed: "אושרה אבל לא נשלחה (נמסרה לבעלים לשליחה ידנית)", delivery_unknown: "לא ידוע אם נשלחה, ממתינה לבדיקת הבעלים", needs_review: "השליחה נקטעה, ממתינה לבדיקת הבעלים", blocked: "נחסמה: הנמען ביקש לא לקבל פניות" };
  for (const a of approvals) {
    const base = { run_id: a.run_id, deal_id: runById.get(a.run_id)?.deal_id || "", who: who(a.from_role) };
    feed.push({ at: a.created, kind: "proposed", text: `פנייה הוכנה וממתינה לאישור: ${a.to_name} · ${a.subject}`, ...base });
    if (a.decided) feed.push({ at: a.decided, kind: a.approved ? "approved" : "rejected", text: `${a.approved ? "הבעלים אישר את הפנייה אל" : "הבעלים דחה את הפנייה אל"} ${a.to_name}`, ...base });
    if (a.status === "sent") feed.push({ at: a.updated, kind: "sent", text: `הפנייה נשלחה אל ${a.to_name}`, ...base });
    else if (PROBLEM[a.status]) feed.push({ at: a.updated, kind: "send_problem", text: `${PROBLEM[a.status]}: ${a.to_name}`, ...base });
  }
  const latestSeen = new Map<string, SeenRow>();
  for (const s of seenAll) latestSeen.set(`${s.kind}:${s.id}`, s);
  for (const s of latestSeen.values()) if (s.decision !== PURSUED) feed.push({ at: s.time, kind: "scout", text: `סקאוט בדק ודילג (${s.decision.replace(/^skipped:\s*/, "")}): ${s.label}`, who: "", run_id: "", deal_id: "" });
  feed.sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0));

  // ---- today's hunt
  const huntRows = [...latestSeen.values()].filter((s) => ilDay(ms(s.time)) === today).sort((a, b) => (a.time < b.time ? 1 : -1));
  const reasons = new Map<string, number>();
  for (const s of huntRows) if (s.decision !== PURSUED) reasons.set(s.decision, (reasons.get(s.decision) || 0) + 1);
  const hunt = { looked: huntRows.length, pursued: huntRows.filter((s) => s.decision === PURSUED).length, skipped: [...reasons.entries()].sort((a, b) => b[1] - a[1]).map(([reason, n]) => ({ reason, n })),
    items: huntRows.slice(0, 40).map((s) => ({ at: s.time, kind: s.kind, label: s.label, score: s.score, decision: s.decision, reasons: s.reasons.slice(0, 8), assignees: s.assignees.map(who).filter(Boolean), run_id: s.run_id, deal_id: s.deal_id })) };

  // ---- waiting for the owner
  const waiting: PendingView[] = approvals.filter((a) => a.status === "pending" || a.status === "needs_review" || a.status === "delivery_unknown").sort((a, b) => (a.created < b.created ? 1 : -1))
    .map((a) => ({ id: a.id, status: a.status, at: a.created, to_name: a.to_name, subject: a.subject, why: a.why, by: who(a.from_role), unverified: a.unverified, deal_id: runById.get(a.run_id)?.deal_id || "", run_title: runById.get(a.run_id)?.title || "" }));

  // ---- seven days, from stored rows only
  const in7 = (iso: string) => { const t = ms(iso); return t >= weekAgo && t <= i.now + DAY; };
  const week = runs.filter((r) => in7(r.started));
  const counters = { days: 7, runs: week.length, scout_runs: week.filter((r) => r.origin === "scout" || scoutOf.has(r.id)).length,
    proposed: approvals.filter((a) => in7(a.created)).length, approved: approvals.filter((a) => a.approved && in7(a.decided)).length, rejected: approvals.filter((a) => a.decided && !a.approved && in7(a.decided)).length,
    // 'Send Guard': one row per state of a send; only a row the guard marked sent counts
    sent: i.guard.filter((g) => g?.[1] === i.ws && g[3] === "sent" && in7(g[0] || "")).length,
    replies: null as null, replies_note: "replies are not read from the mailbox yet",
    est_usd: Math.round(week.reduce((s, r) => s + r.usd, 0) * 100) / 100 };

  return { at: new Date(i.now).toISOString(), day: today, scout_on: i.scoutOn, team, feed: feed.slice(0, 120), hunt, waiting, counters, running: runs.filter(live).length, notes: i.errors || [] };
}
