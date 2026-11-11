import { appendRow, ENGINE_SHEET, readRanges } from "./sheets";
import { readDeal } from "./deal";
import { workspaceOf } from "./users";
import { APPROVALS, loadRuns, startRun, type Run } from "./dealagent";
import { searchTendersSmart } from "./panel";
import { a, dealUrl, tenderUrl } from "./links";
import { agentIo, findTender, send, sendCard, tenderLine } from "./telegram";
import { logActivity } from "./activity";

// Tender projects ("the projector"): one tender worked as a project until its deadline. A project holds a
// schedule of steps counted back from the deadline, the deal file the deal agent writes into, and the runs of the
// agent on it. Every morning the cron checks each active project: the countdown, steps that are due, a tender that
// left the open list or moved its deadline, and what the agent already did (requirements, suppliers, requests for
// quotation, quotes mark their steps done). Nothing is sent to suppliers or buyers from here: the agent only
// proposes messages and the owner approves each one.
// Saved tender searches ("watches") live next to them: the cron reports tenders that are new since the last check.
// Storage: hidden tabs 'Tender Projects' (id, updated, chat, tender_id, status, json; the last row of an id wins)
// and 'Tender Watches' (id, updated, chat, status, json).
const PTAB = "Tender Projects", WTAB = "Tender Watches";
type Row = Record<string, string>;
export type Step = { k: string; due: string; done?: string; auto?: boolean };
export type Project = { id: string; chat: string; email: string; name: string; lang: "he" | "en"; tender_id: string; title: string; buyer: string;
  country: string; value: number; deadline: string; link: string; status: "active" | "paused" | "won" | "lost" | "closed"; created: string;
  deal_id: string; runs: string[]; steps: Step[]; sent: string[]; note?: string };
export type Watch = { id: string; chat: string; lang: "he" | "en"; words: string; country: string; status: "on" | "off"; created: string; seen: string[] };

const STEPS: [string, string, string, number][] = [
  ["docs", "קריאת מסמכי המכרז ותנאי הסף", "Read the tender documents and eligibility", 0.15],
  ["route", "החלטה על דרך כניסה", "Decide the entry route", 0.25],
  ["suppliers", "רשימה קצרה של ספקים", "Supplier shortlist", 0.35],
  ["rfq", "בקשות להצעת מחיר (באישורך)", "Requests for quotation (with your approval)", 0.45],
  ["quotes", "קבלת הצעות מחיר", "Quotes received", 0.65],
  ["gonogo", "תמחור והחלטת Go או No-go", "Pricing and go / no-go", 0.75],
  ["bid", "הכנת מסמכי ההגשה", "Bid documents ready", 0.9],
  ["submit", "הגשה", "Submission", 1],
];
const stepName = (k: string, he: boolean) => { const s = STEPS.find((x) => x[0] === k); return s ? (he ? s[1] : s[2]) : k; };
const esc = (s: unknown) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
const day = (t: number) => new Date(t).toISOString().slice(0, 10);
const daysTo = (d: string) => { const t = Date.parse(d); return Number.isFinite(t) ? Math.ceil((t - Date.now()) / 864e5) : null; };
const money = (n: number) => (!n ? "" : n >= 1e9 ? `$${(n / 1e9).toFixed(1)}B` : n >= 1e6 ? `$${(n / 1e6).toFixed(1)}M` : `$${Math.round(n / 1e3)}K`);
const num = (v: unknown) => { const n = parseFloat(String(v ?? "").replace(/[^0-9.\-]/g, "")); return Number.isFinite(n) ? n : 0; };
const cb = (k: string, id: string) => `${k}:${id}`.slice(0, 64);

/** The schedule, counted back from the deadline (30 days when the deadline is unknown or already passed). */
function schedule(deadline: string, from = Date.now()): Step[] {
  let end = Date.parse(deadline);
  if (!Number.isFinite(end) || end - from < 2 * 864e5) end = from + 30 * 864e5;
  const span = end - from;
  return STEPS.map(([k, , , f]) => ({ k, due: day(k === "submit" ? end - 864e5 : from + span * f) }));
}

// ---- storage --------------------------------------------------------------------------------------------------
export async function saveProject(p: Project) { await appendRow(PTAB, [p.id, new Date().toISOString(), p.chat, p.tender_id, p.status, JSON.stringify(p).slice(0, 48000)]); }
export async function loadProjects(chat?: string): Promise<Project[]> {
  const g = (await readRanges(ENGINE_SHEET, [`'${PTAB}'!A2:F5000`]).catch(() => null))?.[0] || [];
  const last = new Map<string, Project>();
  for (const r of g) { if (!r?.[0] || !r[5]) continue; try { last.set(r[0], JSON.parse(r[5])); } catch { /* a cut row */ } }
  return [...last.values()].filter((p) => !chat || p.chat === chat);
}
async function loadProject(id: string) { return (await loadProjects()).find((p) => p.id === id) || null; }
async function saveWatch(w: Watch) { await appendRow(WTAB, [w.id, new Date().toISOString(), w.chat, w.status, JSON.stringify(w).slice(0, 48000)]); }
export async function loadWatches(chat?: string): Promise<Watch[]> {
  const g = (await readRanges(ENGINE_SHEET, [`'${WTAB}'!A2:E5000`]).catch(() => null))?.[0] || [];
  const last = new Map<string, Watch>();
  for (const r of g) { if (!r?.[0] || !r[4]) continue; try { last.set(r[0], JSON.parse(r[4])); } catch { /* a cut row */ } }
  return [...last.values()].filter((w) => !chat || w.chat === chat);
}

// ---- what the agent already did marks steps done ---------------------------------------------------------------
async function autoProgress(p: Project): Promise<string[]> {
  const marked: string[] = [];
  const recs = (await workspaceOf(p.email).then((ws) => readDeal(p.deal_id, ws)).catch(() => ({ records: [] as { kind: string; data: Record<string, unknown> }[] }))).records;
  const has = { docs: recs.some((r) => r.kind === "requirement"), suppliers: recs.some((r) => r.kind === "party" && String(r.data.role || "") === "supplier"), quotes: recs.some((r) => r.kind === "quote") } as Record<string, boolean>;
  if (p.runs.length) {
    const g = (await readRanges(ENGINE_SHEET, [`'${APPROVALS}'!A2:B5000`]).catch(() => null))?.[0] || [];
    has.rfq = g.some((r) => r && p.runs.includes(String(r[1])));
  }
  for (const s of p.steps) if (!s.done && has[s.k]) { s.done = day(Date.now()); s.auto = true; marked.push(s.k); }
  return marked;
}

// ---- cards ----------------------------------------------------------------------------------------------------
function bar(p: Project) { const n = p.steps.filter((s) => s.done).length; return `${"■".repeat(n)}${"□".repeat(p.steps.length - n)} ${n}/${p.steps.length}`; }
const nextStep = (p: Project) => p.steps.find((s) => !s.done);
function projectText(p: Project) {
  const he = p.lang === "he", today = day(Date.now()), d = daysTo(p.deadline);
  const status = p.status === "active" ? "" : ` · <b>${he ? { paused: "מושהה", won: "זכינו", lost: "הפסדנו", closed: "סגור" }[p.status] : p.status}</b>`;
  const head = `<b>${he ? "פרויקט" : "Project"} ${esc(p.id)}</b>${status}\n<b>${a(tenderUrl(p.tender_id), esc(p.title.slice(0, 140)))}</b>\n`
    + [esc(p.buyer), esc(p.country), money(p.value)].filter(Boolean).join(" · ") + "\n"
    + `${he ? "דדליין" : "Deadline"}: ${esc(p.deadline || "-")}${d !== null ? (he ? ` (עוד ${Math.max(d, 0)} ימים)` : ` (${Math.max(d, 0)} days left)`) : ""}\n${bar(p)}\n\n`;
  const nx = nextStep(p);
  const lines = p.steps.map((s) => {
    const mark = s.done ? "●" : s === nx ? "▶" : s.due < today ? "!" : "○";
    const when = s.done ? (he ? `בוצע ${s.done}${s.auto ? ", זוהה אוטומטית" : ""}` : `done ${s.done}${s.auto ? ", detected" : ""}`) : `${he ? "עד" : "by"} ${s.due}${s.due < today ? (he ? ", באיחור" : ", overdue") : ""}`;
    return `${mark} ${s === nx ? "<b>" : ""}${esc(stepName(s.k, he))}${s === nx ? "</b>" : ""} · ${when}`;
  });
  return head + lines.join("\n") + (p.note ? `\n\n<i>${esc(p.note)}</i>` : "");
}
function projectKeyboard(p: Project) {
  const he = p.lang === "he", nx = nextStep(p);
  const rows: { text: string; callback_data?: string; url?: string }[][] = [];
  if (p.status === "active") {
    if (nx) rows.push([{ text: (he ? "בוצע: " : "Done: ") + stepName(nx.k, he).slice(0, 28), callback_data: cb("pd", p.id) }]);
    rows.push([{ text: he ? "הסוכן ימשיך" : "Agent: continue", callback_data: cb("pa", p.id) }, { text: he ? "ספקים" : "Suppliers", callback_data: cb("ts", p.tender_id) }]);
    rows.push([{ text: he ? "השהה" : "Pause", callback_data: cb("pp", p.id) }, { text: he ? "סיום" : "Close", callback_data: cb("pc", p.id) }, { text: he ? "תיק העסקה" : "Deal file", url: dealUrl(p.deal_id) }]);
  } else rows.push([{ text: he ? "החזר לפעיל" : "Reactivate", callback_data: cb("pr", p.id) }, { text: he ? "תיק העסקה" : "Deal file", url: dealUrl(p.deal_id) }]);
  return rows;
}
async function showProject(p: Project) { return send(p.chat, projectText(p), { reply_markup: { inline_keyboard: projectKeyboard(p) } }); }

// ---- opening a project ----------------------------------------------------------------------------------------
type Who = { chat: string; email: string; name: string; lang: "he" | "en" };
export async function openProject(who: Who, tenderId: string): Promise<void> {
  const he = who.lang === "he";
  const t = await findTender(tenderId);
  if (!t) return send(who.chat, he ? "המכרז לא נמצא בין המכרזים הפתוחים." : "That tender is not among the open tenders.");
  const mine = (await loadProjects(who.chat)).find((p) => p.tender_id === t.id && (p.status === "active" || p.status === "paused"));
  if (mine) { await send(who.chat, he ? "כבר יש פרויקט פתוח על המכרז הזה:" : "There is already a project on this tender:"); return showProject(mine); }
  const id = "P" + Date.now().toString(36).toUpperCase().slice(-6);
  const p: Project = { id, chat: who.chat, email: who.email, name: who.name, lang: who.lang, tender_id: t.id, title: t.title_en || t.title || "", buyer: t.buyer || "",
    country: t.country || "", value: num(t.est_value_usd), deadline: t.deadline || "", link: t.link || "", status: "active", created: new Date().toISOString(),
    deal_id: `PRJ-${id}`, runs: [], steps: schedule(t.deadline || ""), sent: [] };
  // the run works in the workspace of the person who opened the project, never the original one by default
  const run = await startRun(agentIo, { chat: who.chat, email: who.email, name: who.name, lang: who.lang, ws: await workspaceOf(who.email), deal_id: p.deal_id, request: kickoff(p) });
  p.runs.push(run.id);
  await saveProject(p);
  await logActivity({ email: who.email, name: who.name }, "tg_project_open", p.id, t.id);
  await send(who.chat, he
    ? `פתחתי פרויקט על המכרז, עם לוח זמנים לאחור מהדדליין. הסוכן כבר התחיל: קורא את הדרישות, בודק דרכי כניסה ומחפש ספקים. כל פנייה החוצה תגיע אליך לאישור קודם. כל בוקר אשלח כאן תזכורות לפי הלוח.`
    : `Opened a project on this tender, scheduled back from the deadline. The agent has started: reading the requirements, checking entry routes and finding suppliers. Any outgoing message comes to you for approval first. Every morning I will remind you here by the schedule.`);
  return showProject(p);
}
function kickoff(p: Project, extra = "") {
  const open = p.steps.filter((s) => !s.done).map((s) => `${s.k} (due ${s.due})`).join(", ");
  return `Tender project ${p.id} on tender ${p.tender_id}: ${p.title} (buyer ${p.buyer}, ${p.country}, deadline ${p.deadline || "unknown"}).
Work it as a bid project. Open steps: ${open}. In this run: read what the system holds on the tender and record each requirement (eligibility, documents, guarantees) with record kind requirement; assess the entry routes (tender_routes); shortlist suppliers for the exact product and record them as parties with role supplier; propose requests for quotation to the best 2-3 (they wait for the owner's approval); record any quote. Report what is missing for a go / no-go and finish with the next step.${extra ? `\n${extra}` : ""}`;
}

// ---- Telegram callbacks: pv view, pd step done, pa agent, pp pause, pc close menu, pw/pl/px outcome, pr reactivate
export async function projectCallback(who: Who, kind: string, id: string): Promise<boolean> {
  if (kind === "pj") { await openProject(who, id); return true; }
  if (!/^p[vdappcwlxr]$/.test(kind)) return false;
  const he = who.lang === "he";
  const p = await loadProject(id);
  if (!p || p.chat !== who.chat) { await send(who.chat, he ? "הפרויקט לא נמצא." : "Project not found."); return true; }
  p.lang = who.lang;
  if (kind === "pv") { await autoProgress(p).then((m) => (m.length ? saveProject(p) : null)); await showProject(p); return true; }
  if (kind === "pd") { const nx = nextStep(p); if (nx) nx.done = day(Date.now()); await saveProject(p); await showProject(p); return true; }
  if (kind === "pa") {
    const live = (await loadRuns()).find((r: Run) => p.runs.includes(r.id) && (r.status === "running" || r.status === "waiting"));
    if (live) { await send(p.chat, live.status === "waiting" ? (he ? "הסוכן מחכה לתשובה שלך על השאלה האחרונה שלו. ענה כאן בהודעה." : "The agent is waiting for your answer to its last question. Reply here.") : (he ? "הסוכן כבר עובד על הפרויקט." : "The agent is already working on this project.")); return true; }
    const run = await startRun(agentIo, { chat: p.chat, email: p.email, name: p.name, lang: p.lang, ws: await workspaceOf(p.email), deal_id: p.deal_id, request: kickoff(p, "Continue from the deal file: do not repeat what is already recorded; work the next open step.") });
    p.runs.push(run.id); await saveProject(p);
    await send(p.chat, he ? `הסוכן ממשיך מהשלב הבא: ${esc(stepName(nextStep(p)?.k || "", he))}.` : `The agent continues with the next step: ${esc(stepName(nextStep(p)?.k || "", he))}.`);
    return true;
  }
  if (kind === "pp") { p.status = "paused"; await saveProject(p); await send(p.chat, he ? "הפרויקט הושהה. לא אשלח עליו תזכורות." : "Project paused. No reminders for it."); return true; }
  if (kind === "pr") { p.status = "active"; await saveProject(p); await showProject(p); return true; }
  if (kind === "pc") {
    await sendCard(p.chat, he ? "איך הפרויקט הסתיים?" : "How did the project end?", [[{ text: he ? "זכינו" : "Won", callback_data: cb("pw", p.id) }, { text: he ? "הפסדנו" : "Lost", callback_data: cb("pl", p.id) }, { text: he ? "לא הגשנו" : "Did not bid", callback_data: cb("px", p.id) }]]);
    return true;
  }
  p.status = kind === "pw" ? "won" : kind === "pl" ? "lost" : "closed";
  await saveProject(p);
  await logActivity({ email: p.email, name: p.name }, "tg_project_close", p.id, p.status);
  await send(p.chat, he ? "נרשם. הפרויקט נסגר והתוצאה נשמרה בתיק." : "Recorded. The project is closed and the outcome is saved.");
  return true;
}

export async function listProjects(who: Who) {
  const he = who.lang === "he";
  const ps = (await loadProjects(who.chat)).filter((p) => p.status === "active" || p.status === "paused").sort((x, y) => (x.deadline || "9").localeCompare(y.deadline || "9"));
  if (!ps.length) return send(who.chat, he ? "אין פרויקטים פתוחים. פותחים פרויקט מכרטיס של מכרז, בכפתור \"פתח פרויקט\"." : "No open projects. Open one from a tender card with \"Open project\".");
  const text = `<b>${he ? "הפרויקטים שלך" : "Your projects"}</b>\n\n` + ps.map((p, i) => {
    const d = daysTo(p.deadline), nx = nextStep(p);
    return `<b>${i + 1}. ${esc(p.title.slice(0, 80))}</b>\n${esc(p.country)} · ${d !== null ? (he ? `עוד ${Math.max(d, 0)} ימים` : `${Math.max(d, 0)} days left`) : ""} · ${bar(p)}${p.status === "paused" ? (he ? " · מושהה" : " · paused") : ""}\n${nx ? `${he ? "הבא" : "Next"}: ${esc(stepName(nx.k, he))} (${nx.due})` : ""}`;
  }).join("\n\n");
  const kb: { text: string; callback_data: string }[][] = [];
  for (let i = 0; i < ps.length; i += 4) kb.push(ps.slice(i, i + 4).map((p, j) => ({ text: (he ? "פרויקט " : "Project ") + (i + j + 1), callback_data: cb("pv", p.id) })));
  return sendCard(who.chat, text, kb);
}

// ---- watches --------------------------------------------------------------------------------------------------
export async function addWatch(who: Who, words: string, country: string) {
  const he = who.lang === "he";
  if (!words.trim()) return send(who.chat, he ? "על מה לעקוב? למשל:\n/watch data center\n/watch solar KEN" : "What to watch? For example:\n/watch data center\n/watch solar KEN");
  const res = await searchTendersSmart(words, country);
  const w: Watch = { id: "W" + Date.now().toString(36).toUpperCase().slice(-6), chat: who.chat, lang: who.lang, words: words.slice(0, 80), country, status: "on", created: new Date().toISOString(), seen: res.rows.map((r) => r.id).slice(0, 600) };
  await saveWatch(w);
  return sendCard(who.chat, he
    ? `עוקב אחרי "${esc(w.words)}"${country ? ` ב-${country}` : ""}. כרגע יש ${res.rows.length} מכרזים פתוחים. כל בוקר אודיע כאן על מכרזים חדשים.`
    : `Watching "${esc(w.words)}"${country ? ` in ${country}` : ""}. ${res.rows.length} open tenders now. Every morning I will tell you about new ones here.`,
  res.rows.length ? [[{ text: he ? "הצג את הפתוחים עכשיו" : "Show the open ones", callback_data: cb("wv", w.id) }]] : undefined);
}
export async function listWatches(who: Who) {
  const he = who.lang === "he";
  const ws = (await loadWatches(who.chat)).filter((w) => w.status === "on");
  if (!ws.length) return send(who.chat, he ? "אין מעקבים. להוספה: /watch data center" : "No watches. To add one: /watch data center");
  return sendCard(who.chat, `<b>${he ? "מעקבי מכרזים" : "Tender watches"}</b>\n` + ws.map((w, i) => `${i + 1}. ${esc(w.words)}${w.country ? ` · ${w.country}` : ""}`).join("\n"),
    ws.map((w, i) => [{ text: (he ? "הצג " : "Show ") + (i + 1), callback_data: cb("wv", w.id) }, { text: (he ? "הסר " : "Remove ") + (i + 1), callback_data: cb("wx", w.id) }]));
}
export async function watchCallback(who: Who, kind: string, id: string): Promise<boolean> {
  if (kind !== "wv" && kind !== "wx") return false;
  const he = who.lang === "he";
  const w = (await loadWatches(who.chat)).find((x) => x.id === id);
  if (!w) { await send(who.chat, he ? "המעקב לא נמצא." : "Watch not found."); return true; }
  if (kind === "wx") { w.status = "off"; await saveWatch(w); await send(who.chat, he ? `הפסקתי לעקוב אחרי "${esc(w.words)}".` : `Stopped watching "${esc(w.words)}".`); return true; }
  const rows = (await searchTendersSmart(w.words, w.country)).rows.slice(0, 6);
  await tenderCards(who.chat, rows as unknown as Row[], he, `<b>${he ? "פתוחים עכשיו" : "Open now"}</b> · "${esc(w.words)}"`);
  return true;
}
async function tenderCards(chat: string, rows: Row[], he: boolean, head: string) {
  if (!rows.length) return send(chat, he ? "אין כרגע מכרזים פתוחים." : "No open tenders now.");
  const kb: { text: string; callback_data: string }[][] = [];
  for (let i = 0; i < rows.length; i += 3) kb.push(rows.slice(i, i + 3).map((r, j) => ({ text: (he ? "פרטים " : "Details ") + (i + j + 1), callback_data: cb("tn", r.id) })));
  return sendCard(chat, `${head}\n\n${rows.map((r, i) => tenderLine(r, i + 1, he)).join("\n\n")}`, kb);
}

// ---- the morning check (cron) ---------------------------------------------------------------------------------
export async function morningCheck(dry = false): Promise<Record<string, unknown>> {
  const out: Record<string, unknown>[] = [];
  const today = day(Date.now());
  for (const p of (await loadProjects()).filter((x) => x.status === "active")) {
    const he = p.lang === "he", msgs: string[] = [];
    let changed = false;
    const once = (key: string, text: string) => { if (!p.sent.includes(key)) { p.sent.push(key); msgs.push(text); changed = true; } };
    const marked = await autoProgress(p).catch(() => []);
    if (marked.length) { changed = true; msgs.push((he ? "הסוכן השלים: " : "The agent completed: ") + marked.map((k) => stepName(k, he)).join(", ")); }
    const t = await findTender(p.tender_id).catch(() => undefined);
    const d = daysTo(p.deadline);
    if (!t) {
      if (d !== null && d <= 0) once("ended", he ? "הדדליין עבר. איך הסתיים? לחץ \"סיום\" ובחר תוצאה." : "The deadline has passed. How did it end? Tap Close and pick the outcome.");
      else once("gone", he ? "המכרז ירד מרשימת המכרזים הפתוחים. ייתכן שבוטל או שונה. כדאי לבדוק באתר המקור." : "The tender left the open list. It may be cancelled or changed. Worth checking at the source.");
    } else if (t.deadline && t.deadline !== p.deadline) {
      msgs.push(he ? `הדדליין השתנה: ${esc(p.deadline)} ל-${esc(t.deadline)}. עדכנתי את לוח הזמנים.` : `The deadline moved: ${esc(p.deadline)} to ${esc(t.deadline)}. The schedule is updated.`);
      const fresh = schedule(t.deadline);
      p.steps = p.steps.map((s) => (s.done ? s : { ...s, due: fresh.find((f) => f.k === s.k)?.due || s.due }));
      p.deadline = t.deadline; p.sent = p.sent.filter((k) => !/^d\d+$/.test(k)); changed = true;
    }
    const dn = daysTo(p.deadline);
    for (const n of [14, 7, 3, 1]) if (dn !== null && dn <= n && dn > 0) { once(`d${n}`, he ? `נשארו ${dn} ימים להגשה.` : `${dn} days left to submit.`); break; }
    for (const s of p.steps) if (!s.done && s.due <= today) once(`s:${s.k}:${s.due}`, s.due < today ? (he ? `באיחור: ${stepName(s.k, he)} (היה עד ${s.due}).` : `Overdue: ${stepName(s.k, he)} (was due ${s.due}).`) : (he ? `להיום: ${stepName(s.k, he)}.` : `Due today: ${stepName(s.k, he)}.`));
    out.push({ project: p.id, messages: msgs.length });
    if (dry || !msgs.length) continue;
    if (changed) await saveProject(p);
    await send(p.chat, `<b>${he ? "עדכון בוקר" : "Morning update"} · ${a(tenderUrl(p.tender_id), esc(p.title.slice(0, 70)))}</b>\n${msgs.map((m) => `• ${m}`).join("\n")}`,
      { reply_markup: { inline_keyboard: [[{ text: he ? "פתח את הפרויקט" : "Open the project", callback_data: cb("pv", p.id) }]] } });
  }
  for (const w of (await loadWatches()).filter((x) => x.status === "on")) {
    const rows = (await searchTendersSmart(w.words, w.country).catch(() => ({ rows: [] as { id: string }[] }))).rows;
    const fresh = rows.filter((r) => !w.seen.includes(r.id));
    out.push({ watch: w.id, new: fresh.length });
    if (dry || !fresh.length) continue;
    w.seen = [...fresh.map((r) => r.id), ...w.seen].slice(0, 600);
    await saveWatch(w);
    const he = w.lang === "he";
    await tenderCards(w.chat, fresh.slice(0, 6) as unknown as Row[], he, `<b>${he ? `${fresh.length} מכרזים חדשים` : `${fresh.length} new tenders`}</b> · "${esc(w.words)}"${w.country ? ` · ${w.country}` : ""}`);
  }
  return { at: today, items: out };
}
