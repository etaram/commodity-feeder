// The deal agent: the owner writes one request in Telegram ("find 5,000 t of white maize for Kenya", "build a deal on
// this tender") and the agent runs the deal by itself: requirements, suppliers and their contacts, entry routes,
// economics, supplier messages. It reports in Telegram, asks the owner only what it cannot find, and every outgoing
// message waits for the owner's approval button. It never sends, bids or commits on its own.
//
// It runs in short steps (each one Vercel call, at most a few model turns) chained through /api/agent/step, with the
// state in the hidden tab 'Agent Runs' (one row per saved step, the latest row of a run is its state). Facts come
// from the system's own data and from web search with sources; the deal is also saved in the deal records, so the
// panel shows the same deal, but the owner never has to open it.
import { anthropicHeaders, estimateCost, MODEL } from "@/lib/anthropic";
import { appendRow, ENGINE_SHEET, lookupContact, readRanges } from "@/lib/sheets";
import { searchTenders, supplierSearch } from "@/lib/panel";
import { tenders } from "@/lib/index";
import { routeOptions } from "@/lib/routes";
import { cashCheck } from "@/lib/dealstate";
import { clean, readDeal, saveRecord, type Kind } from "@/lib/deal";
import { logActivity } from "@/lib/activity";
import { DEFAULT_WS } from "@/lib/auth";
import { mailReady, sendMail } from "@/lib/mailer";
import { claim } from "@/lib/claims";
import { dealUrl, richText, supplierUrl, tenderUrl } from "@/lib/links";

export const RUNS = "Agent Runs", APPROVALS = "Agent Approvals";
const MAX_TURNS = Number(process.env.AGENT_MAX_TURNS || 24);
const AGENT_MODEL = process.env.AGENT_MODEL || MODEL;

type Block = Record<string, unknown> & { type: string };
type Msg = { role: "user" | "assistant"; content: string | Block[] };
export type Run = { id: string; chat: string; email: string; name: string; lang: "he" | "en"; ws: string; deal_id: string; request: string;
  msgs: Msg[]; turns: number; status: "running" | "waiting" | "done" | "stopped" | "error"; usd: number; started: string; note?: string };

export type Io = { send: (chat: string, text: string, extra?: Record<string, unknown>) => Promise<void>; kick: (id: string) => Promise<void> };

const esc = (s: unknown) => String(s ?? "").replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]!));
const now = () => new Date().toISOString();
type Row = Record<string, string>;
const toObjects = (g: string[][]): Row[] => { const h = g[0] || []; return g.slice(1).map((r) => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""]))); };
const pick = (r: Row, keys: string[]) => Object.fromEntries(keys.filter((k) => r[k]).map((k) => [k, String(r[k]).slice(0, 220)]));

// ---- state -------------------------------------------------------------------------------------------------
export async function saveRun(r: Run) {
  // keep the stored state small: old tool results are shortened (the model has already used them)
  const msgs = r.msgs.map((m, i) => (i < r.msgs.length - 6 && Array.isArray(m.content)
    ? { ...m, content: m.content.map((b) => (b.type === "tool_result" && String(b.content || "").length > 600 ? { ...b, content: String(b.content).slice(0, 600) + " ...(shortened)" } : b)) } : m));
  let json = JSON.stringify({ ...r, msgs });
  if (json.length > 48000) json = JSON.stringify({ ...r, msgs: [msgs[0], { role: "assistant", content: "(earlier steps shortened)" }, ...msgs.slice(-8)] }).slice(0, 49000);
  await appendRow(RUNS, [r.id, now(), r.chat, r.email, r.status, r.turns, json]);
}
export async function loadRuns(): Promise<Run[]> {
  const g = (await readRanges(ENGINE_SHEET, [`'${RUNS}'!A2:G5000`]).catch(() => null))?.[0] || [];
  const last = new Map<string, Run>();
  for (const row of g) { if (!row?.[0] || !row[6]) continue; try { last.set(row[0], JSON.parse(row[6])); } catch { /* a cut row */ } }
  return [...last.values()];
}
export async function loadRun(id: string) { return (await loadRuns()).find((r) => r.id === id) || null; }

// ---- tools -------------------------------------------------------------------------------------------------
const TOOLS = [
  { name: "search_suppliers", description: "Suppliers from the system's supplier index for an English product phrase, ranked by exact product fit (match: supported, plausible, related, incompatible, with the reason and gaps). Optional origin_country ISO3, kind maker|trader.", input_schema: { type: "object", properties: { product: { type: "string" }, origin_country: { type: "string" }, kind: { type: "string" } }, required: ["product"] } },
  { name: "supplier_contact", description: "Contact details the system holds for one supplier (email, phone, website, address, legal id). country: ISO3 as returned by search_suppliers.", input_schema: { type: "object", properties: { company: { type: "string" }, country: { type: "string" } }, required: ["company"] } },
  { name: "search_tenders", description: "Open tenders from the system, ranked by deal fit. words: English product words; country: ISO3 or empty.", input_schema: { type: "object", properties: { words: { type: "string" }, country: { type: "string" } }, required: ["words"] } },
  { name: "tender_routes", description: "Entry routes for one tender id (direct bid, manufacturer with Sinder as agent, local partner, sub-supply to the winner) with verdict, basis, assumptions, missing items and next action.", input_schema: { type: "object", properties: { tender_id: { type: "string" } }, required: ["tender_id"] } },
  { name: "deal_economics", description: "Indicative deal economics in USD: gross profit, financing cost on the negative cash balance (daily simple interest), net, peak funding and warnings. Days are counted from the order.", input_schema: { type: "object", properties: { sale_price: { type: "number" }, cost_goods: { type: "number" }, freight: { type: "number" }, other_costs: { type: "number" }, fin_rate_pct: { type: "number" }, supplier_pay_day: { type: "number" }, customer_pay_day: { type: "number" }, funding_limit: { type: "number" } }, required: ["sale_price", "cost_goods"] } },
  { name: "record", description: "Save a fact to this deal's records. kind requirement: {item, mandatory, status (met|not_met|unknown|missing), source_doc}. kind party: {role (supplier|buyer|partner|finance|logistics), name, country ISO3, email, phone, website, source, note}. kind quote: {supplier, product, qty, unit, unit_price, currency, incoterm, named_place, valid_until YYYY-MM-DD, availability (confirmed|unconfirmed), source_ref}.", input_schema: { type: "object", properties: { kind: { type: "string", enum: ["requirement", "party", "quote"] }, data: { type: "object" } }, required: ["kind", "data"] } },
  { name: "propose_message", description: "Prepare one outgoing message (a request for quotation to a supplier, a question to a buyer). It is NOT sent: the owner gets it with Approve and Reject buttons. Continue working after proposing.", input_schema: { type: "object", properties: { to_name: { type: "string" }, to_email: { type: "string" }, language: { type: "string" }, subject: { type: "string" }, body: { type: "string" }, why: { type: "string" } }, required: ["to_name", "subject", "body", "why"] } },
  { name: "ask_owner", description: "Ask the owner one short question you cannot answer from the data (quantity, price target, buyer, timing). The run pauses until the owner answers in Telegram.", input_schema: { type: "object", properties: { question: { type: "string" } }, required: ["question"] } },
  { name: "report", description: "Send the owner a short progress update (2-5 lines) when you reach a result worth knowing.", input_schema: { type: "object", properties: { text: { type: "string" } }, required: ["text"] } },
  { name: "finish", description: "End the run with the final summary for the owner: what was found, what is ready, what is waiting for approval, what is missing and the next step.", input_schema: { type: "object", properties: { summary: { type: "string" } }, required: ["summary"] } },
];

function system(r: Run) {
  const he = r.lang === "he";
  return `You are Sinder's deal agent. Sinder is an Israeli international procurement and trading firm. The owner gave you one request and you run the deal end to end by yourself, without asking him to use any system.
Work in this order, skipping what does not apply: 1) state the requirement (product, grade, quantity, destination, timing) and record it; ask_owner only for facts that change the work and cannot be found; 2) if it is a tender, read it (search_tenders) and check entry routes (tender_routes); 3) find suppliers (search_suppliers), keep only those whose match is supported or plausible, prefer makers, and get their contacts (supplier_contact; web search for the official sales contact when the system has none); record the usable ones as parties; 4) compute indicative economics when you have a price basis (deal_economics); 5) propose_message one request for quotation per selected supplier (3 to 6 suppliers), in English or the supplier's business language, saying it is a request for information and not an order; 6) finish.
Rules: facts only from the tools and web search results, with the source; never invent a company, contact, price or date; a directory row, a name match or an indicative price is not a verified fact; never call a fit "verified"; a restriction on one route is not a rejection of the deal. Nothing is ever sent by you: propose_message only prepares it for the owner's approval. Never commit, bid, accept terms or create accounts.
Talk to the owner (report, ask_owner, finish) in ${he ? "simple, plain Hebrew, short lines, no jargon, no English terms where a Hebrew word exists, no em-dashes, no emojis" : "plain English, short lines"}. Use report after each main stage. Make names clickable: write a supplier, a tender or the deal as [name](open link), using the "open" links the tools return; the deal page is ${dealUrl(r.deal_id)}. The deal id is ${r.deal_id}. Today is ${now().slice(0, 10)}.`;
}

async function runTool(r: Run, io: Io, name: string, x: Record<string, unknown>): Promise<string> {
  const s = (k: string, n = 200) => String(x[k] ?? "").slice(0, n);
  if (name === "search_suppliers") {
    const res = await supplierSearch({ text: s("product", 160), strict: true, n: 12, originCountry: s("origin_country", 3).toUpperCase(), kind: (["maker", "trader"].includes(s("kind")) ? s("kind") : "") as "maker" | "trader" | "" } as never);
    const rows = toObjects(res.values).filter((y) => y.match !== "incompatible").slice(0, 12);
    return JSON.stringify({ total: res.total, suppliers: rows.map((y) => ({ ...pick(y, ["supplier", "country", "type", "tier", "products", "website", "match", "match_why", "match_gaps", "match_conflicts"]), open: supplierUrl(y.supplier, y.country) })) });
  }
  if (name === "supplier_contact") return JSON.stringify((await lookupContact(s("company"), s("country", 3).toUpperCase()).catch(() => null)) || { note: "no contact on record; try web search for the official sales contact" });
  if (name === "search_tenders") {
    const g = await searchTenders([[s("words", 160), "", s("country", 3).toUpperCase()], ["", "", ""], ["", "", ""], ["", "", ""], ["", "", ""]]);
    return JSON.stringify(toObjects(g).slice(0, 8).map((y) => ({ ...pick(y, ["id", "title_en", "title", "buyer", "country", "est_value_usd", "deadline", "access", "route", "fit", "link"]), open: y.id ? tenderUrl(y.id) : "" })));
  }
  if (name === "tender_routes") {
    const t = (await tenders()).find((y) => y.id === s("tender_id", 120));
    if (!t) return "tender not found in the system";
    const routes = routeOptions({ country: t.c, access: t.acc === "set-aside" ? "reserved for local bidders (set-aside)" : t.acc === "intl" ? "international bidding" : "", title: t.t, sector: t.s, value_usd: t.v, stage: t.st });
    return JSON.stringify({ tender: { id: t.id, title: t.t, country: t.c, buyer: t.b, value_usd: t.v, deadline: t.dl, link: t.l, open: tenderUrl(t.id) }, routes });
  }
  if (name === "deal_economics") {
    const n = (k: string, d = 0) => (Number.isFinite(Number(x[k])) && x[k] !== "" && x[k] != null ? Number(x[k]) : d);
    const sale = n("sale_price"), cost = n("cost_goods") + n("freight") + n("other_costs");
    const c = cashCheck([{ day: n("supplier_pay_day", 0), amount: -cost }, { day: n("customer_pay_day", 60), amount: sale }], n("fin_rate_pct", 10) / 100, x.funding_limit == null ? null : n("funding_limit"));
    return JSON.stringify({ label: "indicative estimate from the stated assumptions", gross_profit: Math.round(sale - cost), finance_cost: Math.round(c.finance_cost), net: Math.round(sale - cost - c.finance_cost), peak_funding: Math.round(c.peak_funding), funding_capacity: c.funding_capacity, warnings: c.warnings });
  }
  if (name === "record") {
    const kind = s("kind", 20) as Kind;
    if (!["requirement", "party", "quote"].includes(kind)) return "kind must be requirement, party or quote";
    const c = clean(kind, (x.data || {}) as Record<string, unknown>);
    if (!c.ok) return "not saved: " + c.error;
    const cur = await readDeal(r.deal_id, r.ws);
    const rid = `${kind[0].toUpperCase()}${Date.now().toString(36).toUpperCase()}`;
    await saveRecord(r.deal_id, kind, rid, 1 + (cur.records.find((y) => y.kind === kind && y.record_id === rid)?.version || 0), c.status, c.data, r.email, "deal agent", r.ws);
    return `saved ${kind} ${rid}`;
  }
  if (name === "propose_message") {
    const id = "M" + Date.now().toString(36).toUpperCase();
    const m = { to_name: s("to_name"), to_email: s("to_email", 120), language: s("language", 30), subject: s("subject", 200), body: s("body", 4000), why: s("why", 400) };
    await appendRow(APPROVALS, [id, r.id, r.chat, now(), "pending", JSON.stringify(m)]);
    const he = r.lang === "he";
    await io.send(r.chat, `${he ? "<b>פנייה לאישור</b>" : "<b>Message for approval</b>"}\n${esc(he ? "אל" : "To")}: ${esc(m.to_name)}${m.to_email ? ` &lt;${esc(m.to_email)}&gt;` : ""}\n${esc(he ? "למה" : "Why")}: ${esc(m.why)}\n\n<b>${esc(m.subject)}</b>\n${esc(m.body)}`,
      { reply_markup: { inline_keyboard: [[{ text: he ? "אשר" : "Approve", callback_data: `ag:ok:${id}` }, { text: he ? "דחה" : "Reject", callback_data: `ag:no:${id}` }],
        [{ text: he ? "פתח את הספק במערכת" : "Open the supplier", url: supplierUrl(m.to_name) }, { text: he ? "פתח את העסקה" : "Open the deal", url: dealUrl(r.deal_id) }]] } });
    return `proposed ${id}; waiting for the owner's approval (not sent). Continue with the rest of the work.`;
  }
  if (name === "report") { await io.send(r.chat, richText(s("text", 2000)), dealButton(r)); return "reported"; }
  return "unknown tool";
}

// ---- running -----------------------------------------------------------------------------------------------
const dealButton = (r: Run) => ({ reply_markup: { inline_keyboard: [[{ text: r.lang === "he" ? "פתח את העסקה במערכת" : "Open the deal", url: dealUrl(r.deal_id) }]] } });

export async function startRun(io: Io, o: { chat: string; email: string; name: string; lang: "he" | "en"; ws?: string; request: string }) {
  const id = "AG" + Date.now().toString(36).toUpperCase();
  const r: Run = { id, chat: o.chat, email: o.email, name: o.name, lang: o.lang, ws: o.ws || DEFAULT_WS, deal_id: "AGENT-" + id, request: o.request.slice(0, 1500),
    msgs: [{ role: "user", content: o.request.slice(0, 1500) }], turns: 0, status: "running", usd: 0, started: now() };
  await saveRecord(r.deal_id, "stage", "stage", 1, "lead", { stage: "lead", title: o.request.slice(0, 240), next_step: "deal agent running", note: "opened by the deal agent from Telegram" }, o.email, "deal agent", r.ws).catch(() => {});
  await saveRun(r);
  await logActivity({ email: o.email, name: o.name }, "agent_start", id, o.request.slice(0, 200));
  await io.kick(id);
  return r;
}

export async function resume(io: Io, r: Run, answer: string) {
  // the paused turn ended with ask_owner: its tool_result carries the answer
  const last = r.msgs[r.msgs.length - 1];
  if (last?.role === "user" && Array.isArray(last.content) && last.content.some((b) => b.type === "tool_result" && /waiting for the owner/.test(String(b.content)))) {
    last.content = last.content.map((b) => (b.type === "tool_result" && /waiting for the owner/.test(String(b.content)) ? { ...b, content: `The owner answered: ${answer.slice(0, 1500)}` } : b));
  } else if (last?.role === "user" && Array.isArray(last.content)) last.content.push({ type: "text", text: `The owner adds: ${answer.slice(0, 1500)}` });
  else r.msgs.push({ role: "user", content: `The owner adds: ${answer.slice(0, 1500)}` });
  r.status = "running";
  await saveRun(r);
  await io.kick(r.id);
}

/** One step: up to a few model turns within the time budget, then save and chain the next step. */
export async function step(io: Io, id: string, budgetMs = 200_000) {
  // one step of a run at a time: a duplicate kick or a Telegram retry finds the run claimed and does nothing
  const lock = await claim(`run:${id}`, budgetMs + 60_000).catch(() => ({ ok: true, release: async () => {} }));
  if (!lock.ok) return;
  let again = false;
  try { again = await stepLocked(io, id, budgetMs); } finally { await lock.release(); }
  if (again) await io.kick(id);  // the next step claims the run after this one released it
}
async function stepLocked(io: Io, id: string, budgetMs: number): Promise<boolean> {
  const r = await loadRun(id);
  if (!r || r.status !== "running") return false;
  const t0 = Date.now(), he = r.lang === "he";
  try {
    while (Date.now() - t0 < budgetMs - 60_000) {
      if (r.turns >= MAX_TURNS) {
        r.status = "done";
        await io.send(r.chat, he ? "הגעתי למספר הצעדים המרבי לבקשה אחת. מה שנמצא שמור, ואפשר לבקש ממני להמשיך." : "Reached the step limit for one request. What was found is saved; ask me to continue.");
        break;
      }
      r.turns++;
      const t1 = Date.now();
      const res = await fetch("https://api.anthropic.com/v1/messages", { method: "POST", headers: anthropicHeaders(),
        body: JSON.stringify({ model: AGENT_MODEL, max_tokens: 3000, system: system(r), tools: [...TOOLS, { type: "web_search_20250305", name: "web_search", max_uses: 3 }], messages: r.msgs }) });
      const j = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(`AI ${res.status}: ${String(j?.error?.message || "").slice(0, 160)}`);
      const usd = estimateCost(j.usage || {}); r.usd += usd;
      void appendRow("AI Usage", [now(), "deal agent", r.ws, AGENT_MODEL, j.usage?.input_tokens || 0, j.usage?.output_tokens || 0, j.usage?.cache_read_input_tokens || 0, j.usage?.server_tool_use?.web_search_requests || 0, Math.round(usd * 1e5) / 1e5, Date.now() - t1, "ok"]).catch(() => {});
      // keep only text (without citation payloads) and our own tool calls: web search results are not replayed
      const content: Block[] = (j.content || []).filter((b: Block) => b.type === "text" || b.type === "tool_use").map((b: Block) => (b.type === "text" ? { type: "text", text: String(b.text || "") } : b))
        .filter((b: Block) => b.type !== "text" || String(b.text).trim());
      const srcs = (j.content || []).flatMap((b: Block) => (b.type === "text" && Array.isArray(b.citations) ? (b.citations as { url?: string }[]).map((c) => c.url).filter(Boolean) : [])) as string[];
      if (srcs.length && content.length && content[content.length - 1].type === "text") content.push({ type: "text", text: `Sources: ${[...new Set(srcs)].slice(0, 5).join(" ")}` });
      if (!content.length) content.push({ type: "text", text: "(no output)" });
      r.msgs.push({ role: "assistant", content });
      const uses = content.filter((b) => b.type === "tool_use") as (Block & { id: string; name: string; input: Record<string, unknown> })[];
      if (j.stop_reason === "pause_turn") { r.msgs.push({ role: "user", content: "Continue." }); continue; }
      if (!uses.length) {
        // the model answered in text without finishing: treat the text as the summary
        const txt = content.map((b) => String(b.text || "")).join("\n").trim();
        if (txt) await io.send(r.chat, richText(txt), dealButton(r));
        r.status = "done"; break;
      }
      const results: Block[] = [];
      let waiting = false, finished = "";
      for (const u of uses) {
        if (u.name === "finish") { finished = String(u.input.summary || ""); results.push({ type: "tool_result", tool_use_id: u.id, content: "finished" }); continue; }
        if (u.name === "ask_owner") { waiting = true; await io.send(r.chat, `<b>${he ? "שאלה" : "Question"}</b>\n${esc(u.input.question)}`); results.push({ type: "tool_result", tool_use_id: u.id, content: "waiting for the owner's answer" }); continue; }
        let out: string;
        try { out = await runTool(r, io, u.name, u.input || {}); } catch (e) { out = "error: " + String((e as Error).message || e).slice(0, 200); }
        results.push({ type: "tool_result", tool_use_id: u.id, content: out.slice(0, 6000) });
      }
      r.msgs.push({ role: "user", content: results });
      if (finished) { await io.send(r.chat, `<b>${he ? "סיכום העסקה" : "Deal summary"}</b>\n${richText(finished)}`, dealButton(r)); r.status = "done"; break; }
      if (waiting) { r.status = "waiting"; break; }
    }
  } catch (e) {
    r.status = "error"; r.note = String((e as Error).message || e).slice(0, 300);
    await io.send(r.chat, (he ? "הסוכן נעצר בגלל תקלה: " : "The agent stopped on an error: ") + esc(r.note));
  }
  await saveRun(r);
  return r.status === "running";
}

// ---- approvals ---------------------------------------------------------------------------------------------
const STUCK_MS = 10 * 60_000;
const label = (st: string, he: boolean) => (he ? ({ sent: "נשלחה", rejected: "נדחתה", send_failed: "לא נשלחה (נמסרה לך לשליחה ידנית)", sending: "בשליחה", needs_review: "ממתינה לבדיקה שלך", approved: "אושרה" } as Record<string, string>)[st] || st : st);

/** The owner's decision on one proposed message. States: pending → sending → sent | send_failed, or pending → rejected.
 *  A message is sent at most once: the decision is claimed first (a double press or a retry finds it claimed), and a
 *  send that never reported back (the call died mid-way) becomes needs_review, never a silent second send. */
export async function decide(io: Io, chat: string, approvalId: string, ok: boolean, again = false) {
  const g = (await readRanges(ENGINE_SHEET, [`'${APPROVALS}'!A2:F5000`]).catch(() => null))?.[0] || [];
  const mine = g.filter((x) => x[0] === approvalId);
  const row = mine[mine.length - 1], first = mine[0];
  if (!row || row[2] !== chat) return io.send(chat, "-");
  const m = JSON.parse(first[5] || "{}");
  const run = await loadRun(row[1]);
  const he = run ? run.lang === "he" : true;
  let st = row[4];
  // a send that started and never finished: say so, and let the owner decide after checking his Sent folder
  if (st === "sending" && Date.now() - Date.parse(row[3] || "") > STUCK_MS) {
    await appendRow(APPROVALS, [approvalId, row[1], chat, now(), "needs_review", first[5]]);
    st = "needs_review";
  }
  if (st === "needs_review" && again) st = "pending";
  if (st === "needs_review") return io.send(chat, he ? `השליחה אל ${esc(m.to_name)} לא דיווחה אם הסתיימה. בדוק בתיקיית "נשלח" ב-Zoho. אם המייל לא שם, אפשר לשלוח שוב.` : `The send to ${esc(m.to_name)} never reported back. Check the Sent folder in Zoho; if it is not there, send again.`,
    { reply_markup: { inline_keyboard: [[{ text: he ? "שלח שוב" : "Send again", callback_data: `ag:re:${approvalId}` }, { text: he ? "דחה" : "Reject", callback_data: `ag:no:${approvalId}` }]] } });
  if (st !== "pending") return io.send(chat, he ? `כבר טופל: ${label(st, true)}.` : `Already handled: ${st}.`);
  const lock = await claim(`appr:${approvalId}`, STUCK_MS);
  if (!lock.ok) return io.send(chat, he ? "ההחלטה על הפנייה הזו כבר בטיפול." : "This message is already being handled.");
  try {
    if (!ok) { await appendRow(APPROVALS, [approvalId, row[1], chat, now(), "rejected", first[5]]); return io.send(chat, he ? `נדחתה: ${esc(m.to_name)}. הפנייה לא תצא.` : `Rejected: ${esc(m.to_name)}. It will not be sent.`); }
    const ready = mailReady() && !!m.to_email;
    if (ready) await appendRow(APPROVALS, [approvalId, row[1], chat, now(), "sending", first[5]]);
    const res = ready ? await sendMail({ to: m.to_email, subject: m.subject || "", text: m.body || "" }) : { ok: false as const, error: m.to_email ? "mailbox not configured" : "no recipient address" };
    await appendRow(APPROVALS, [approvalId, row[1], chat, now(), res.ok ? "sent" : "send_failed", JSON.stringify({ ...m, mail_id: res.ok ? res.id : "", error: res.ok ? "" : res.error })]);
    if (run) {
      // the supplier moves to contacted when the request actually left; a failed send leaves it a candidate
      const cur = (await readDeal(run.deal_id, run.ws).catch(() => ({ records: [] as { kind: string; record_id: string; version: number; status: string }[] }))).records;
      const prev = cur.filter((x) => x.kind === "party" && x.record_id === "P" + approvalId).sort((x, y) => y.version - x.version)[0];
      const status = res.ok ? "contacted" : (prev?.status || "candidate");
      await saveRecord(run.deal_id, "party", "P" + approvalId, (prev?.version || 0) + 1, status, { role: "supplier", name: m.to_name || "-", email: m.to_email || "", status,
        note: `RFQ ${res.ok ? "sent" : "approved, not sent"} ${now().slice(0, 10)}`, source: "deal agent" }, run.email, "deal agent", run.ws).catch(() => {});
    }
    if (res.ok) return io.send(chat, he ? `נשלח אל ${esc(m.to_name)} &lt;${esc(m.to_email)}&gt; מהתיבה ${esc(process.env.ZOHO_SMTP_USER || "")}. תשובה תגיע לתיבה שלך.` : `Sent to ${esc(m.to_name)} &lt;${esc(m.to_email)}&gt; from ${esc(process.env.ZOHO_SMTP_USER || "")}. A reply will reach your mailbox.`);
    return io.send(chat, (he ? `אושרה, אבל לא נשלחה (${esc(res.error)}). הנה ההודעה לשליחה ידנית${m.to_email ? ` אל ${esc(m.to_email)}` : ""}:` : `Approved but not sent (${esc(res.error)}). Here is the message to send yourself${m.to_email ? ` to ${esc(m.to_email)}` : ""}:`)
      + `\n\n<b>${esc(m.subject)}</b>\n<pre>${esc(m.body)}</pre>`);
  } finally { await lock.release(); }
}

/** A run that stopped on an error goes on from where it stopped (the owner's /retry). */
export async function retryLatest(io: Io, chat: string) {
  const r = (await loadRuns()).filter((x) => x.chat === chat && x.status === "error").sort((a, b) => (a.started < b.started ? 1 : -1))[0];
  if (!r) return false;
  r.status = "running"; r.note = "";
  if (r.turns >= MAX_TURNS) r.turns = MAX_TURNS - 6;
  await saveRun(r);
  await io.kick(r.id);
  return true;
}

export async function stopLatest(chat: string) {
  const runs = (await loadRuns()).filter((r) => r.chat === chat && (r.status === "running" || r.status === "waiting"));
  for (const r of runs) { r.status = "stopped"; await saveRun(r); }
  return runs.length;
}
export async function waitingRun(chat: string) {
  return (await loadRuns()).filter((r) => r.chat === chat && r.status === "waiting").sort((a, b) => (a.started < b.started ? 1 : -1))[0] || null;
}
