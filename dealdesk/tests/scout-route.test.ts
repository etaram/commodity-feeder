// The scouts' round (lib/scoutrun.ts) and its cron route, over the in-memory sheet (tests/build-agent-test.mjs): flag
// off = nothing happens; flag on = runs are started up to the limits, every decision is recorded, and a second call
// starts nothing new. Runs are started through the real startRun with a recording Telegram stand-in, and a scripted
// model shows that a scout run keeps to its own step and cost limits. No network, no model; all names are made up.
import { NextRequest } from "next/server";
import { GET } from "@/app/api/cron/scout/route";
import { readSeen, scoutNote, scoutRound, tenderSignal, type Owner, type ScoutDeps, type StartArgs } from "@/lib/scoutrun";
import { loadRun, loadRuns, startRun, step } from "@/lib/dealagent";
import { appendRow } from "@/lib/sheets";
import { LIMIT, PURSUED, SCOUT_SEEN, seenToCells } from "@/lib/scout";
import type { Winner } from "@/lib/index";
import { TABS } from "./mocks/sheets";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.AUTH_SECRET = "test-secret";
process.env.GOOGLE_SERVICE_ACCOUNT_JSON = "{}";
process.env.ANTHROPIC_API_KEY = "test";
process.env.CRON_SECRET = "cron-secret";

const sent: { chat: string; text: string }[] = [], kicks: string[] = [], notes: string[] = [];
const io = { send: async (chat: string, text: string) => { sent.push({ chat, text }); }, kick: async (id: string) => { kicks.push(id); } };
const OWNER: Owner = { chat: "C1", email: "owner@sinder.test", name: "Owner", lang: "he", ws: "sinder" };
let clock = Date.parse("2026-11-12T08:00:00Z");
const win = (n: number, o: Partial<Winner> = {}): Winner => ({ d: "2026-11-10", w: [`Example Contractor ${n} Ltd`], wc: "KEN", c: "KEN", b: "Example Roads Authority", t: `Road works lot ${n}: bitumen and steel`, v: n * 10_000_000, k: "contractor",
  n: ["bitumen", "steel"], cm: "", s: "Example Bank", l: "https://awards.example/" + n, id: `AW-${n}`, sc: 50, ws: "https://contractor.example", ce: ["procurement@contractor.example"], ...o });
const trow = (o: Record<string, string> = {}) => ({ id: "TN-1", new: "NEW", stage: "tender", title_en: "Supply of water pumps", country: "IND", buyer: "Example Water Board", est_value_usd: "3,000,000", days_left: "25", fit: "70", sector: "Water & wastewater",
  access: "International competitive bidding", decision: "Pursue", commodity: "pumps", buyer_awards_12m: "3", link: "https://tenders.example/1", ...o });
let data: { winners: Winner[]; tenders: Record<string, string>[] } = { winners: [], tenders: [] };
let budget = { spent_usd: 0, alert_usd: 15 }, owner: Owner | null = OWNER, startFails = false;
const starts: StartArgs[] = [];
const deps = (): ScoutDeps => ({
  now: () => clock, owner: async () => owner, winners: async () => data.winners, tenders: async () => data.tenders, buyerAwards: async () => 9,
  focus: async () => ({ words: [], partners: [], excluded: [] }), budget: async () => budget, seen: readSeen,
  record: async (row) => { await appendRow(SCOUT_SEEN, seenToCells(row)); },
  start: async (o) => { starts.push(o); if (startFails) throw new Error("no model key"); clock += 1; await new Promise((r) => setTimeout(r, 3)); const r = await startRun(io, o); return { id: r.id, deal_id: r.deal_id }; },
  notify: async (_o, p, id) => { notes.push(`${id} ${scoutNote(p, true)}`); },
  claim: async () => ({ ok: true, release: async () => {} }),
});
const seenRows = () => (TABS[SCOUT_SEEN] || []).map((r) => r.map(String));
const decisions = () => seenRows().map((r) => r[5]);
const req = (auth?: string, q = "") => new NextRequest("http://localhost/api/cron/scout" + q, auth ? { headers: { authorization: auth } } : {});
const reset = () => { for (const k of Object.keys(TABS)) delete TABS[k]; starts.length = 0; kicks.length = 0; notes.length = 0; sent.length = 0; budget = { spent_usd: 0, alert_usd: 15 }; owner = OWNER; startFails = false; clock = Date.parse("2026-11-12T08:00:00Z"); };
const env = (o: Record<string, string>) => { for (const k of Object.keys(process.env)) if (/^SCOUT/.test(k)) delete process.env[k]; Object.assign(process.env, o); };

(async () => {
  // ---- the route: secret and flag
  env({});
  ok((await GET(req())).status === 401 && (await GET(req("Bearer wrong"))).status === 401, "the cron route refuses a call without the cron secret");
  const off = await GET(req("Bearer cron-secret")), offJ = await off.json();
  ok(off.status === 200 && offJ.scout === "off" && offJ.started === 0 && Object.keys(TABS).length === 0, "flag off: the route answers and nothing is read, written or started");
  data = { winners: [win(1), win(2), win(3), win(4)], tenders: [trow()] };
  const offRound = await scoutRound(deps());
  ok(offRound.scout === "off" && starts.length === 0 && !TABS[SCOUT_SEEN] && !TABS["Agent Runs"], "flag off: a round with good signals in the data starts no run and records nothing");

  // ---- flag on: one lead a round by default, up to the daily limit
  reset(); env({ SCOUT: "on", SCOUT_MAX_RUNS_PER_DAY: "2" }); data.tenders = [];
  const r1 = await scoutRound(deps());
  ok(r1.started === 1 && starts.length === 1 && kicks.length === 1 && (await loadRuns()).length === 1, "flag on: the first round starts one run (one lead at a time)");
  const run1 = (await loadRuns())[0];
  ok(run1.origin === "scout" && run1.max_turns === 12 && run1.max_usd === 1 && run1.chat === "C1" && run1.ws === "sinder" && run1.lang === "he" && /^Scout lead/.test(run1.request), "the run is a deal agent run for the owner's chat, marked scout, with the scout's turn and cost limits");
  ok(starts[0].request.includes("Example Contractor 4 Ltd") && /buyer has 9 awards in the award data: \+5/.test(starts[0].request), "the best signal goes first, and the buyer's record read for it is part of the reasons");
  const p1 = seenRows().filter((r) => r[5] === PURSUED);
  ok(p1.length === 2 && p1[0][6] === "" && p1[1][6] === run1.id && p1[1][10] === run1.deal_id && p1[1][7] === "relations_africa,analyst" && p1[1][1] === "sinder" && p1[1][2] === "winner", "the decision is recorded before the run starts and again with the run id, the assignees and the deal");
  ok(decisions().filter((d) => d === LIMIT).length === 3 && seenRows().find((r) => r[5] === LIMIT)![9].startsWith("one round starts at most 1"), "the other good signals are recorded as held by the limit, with which limit");
  ok(notes.length === 1 && /סקאוט פתח ליד/.test(notes[0]) && /Grace Mwangi/.test(notes[0]) && notes[0].startsWith(run1.id), "the owner gets a short note in Hebrew naming who leads it");
  ok(TABS["Agent Approvals"] === undefined && TABS["Send Guard"] === undefined && sent.length === 0, "starting a run proposes nothing and sends nothing");
  const r2 = await scoutRound(deps());
  ok(r2.started === 1 && starts.length === 2 && starts[1].request.includes("Example Contractor 3 Ltd"), "the next round takes the next signal, not the same one");
  const before = seenRows().length;
  const r3 = await scoutRound(deps());
  ok(r3.started === 0 && starts.length === 2 && /daily run limit/.test(r3.note) && seenRows().length === before, "at the daily limit a round starts nothing; signals already recorded as held today are not written again");
  const r4 = await scoutRound(deps());
  ok(r4.started === 0 && (await loadRuns()).length === 2 && seenRows().length === before, "a further call the same day changes nothing");

  // ---- the next day the held signals are taken, the pursued ones never again
  clock = Date.parse("2026-11-13T08:00:00Z");
  const r5 = await scoutRound(deps());
  const third = starts[2]?.request || "";
  ok(r5.started === 1 && !third.includes("Contractor 4 Ltd") && !third.includes("Contractor 3 Ltd"), "the next day a signal that was held is started; one already pursued is not started again");

  // ---- every limit in one call; idempotent on a second call
  reset(); env({ SCOUT: "on", SCOUT_MAX_RUNS_PER_ROUND: "5" });
  const a1 = await scoutRound(deps());
  ok(a1.started === 3 && (await loadRuns()).length === 3 && new Set(starts.map((s) => s.request.split("\n")[0])).size === 3, "with a wider round the default daily limit of 3 runs holds");
  const a2 = await scoutRound(deps());
  ok(a2.started === 0 && starts.length === 3 && (await loadRuns()).length === 3, "a second call starts nothing new");
  ok(decisions().filter((d) => d === LIMIT).length === 1 && seenRows().some((r) => r[5] === LIMIT && /daily run limit reached \(3 a day\)/.test(r[9])), "what the limit held back is on record as skipped: limit");

  // ---- one signal only: handled once
  reset(); data = { winners: [win(7)], tenders: [] };
  ok((await scoutRound(deps())).started === 1 && (await scoutRound(deps())).started === 0 && starts.length === 1, "a signal handled once is not started again while the limits still have room");

  // ---- the AI budget
  reset(); data = { winners: [win(1), win(2)], tenders: [] }; budget = { spent_usd: 14.5, alert_usd: 15 };
  const b1 = await scoutRound(deps());
  ok(b1.started === 0 && starts.length === 0 && /AI budget/.test(b1.note) && decisions().every((d) => d === LIMIT) && decisions().length === 2, "today's AI spend leaves no room for a run: nothing starts and the signals are recorded as skipped: limit");
  const n1 = seenRows().length; await scoutRound(deps());
  ok(seenRows().length === n1 && starts.length === 0, "and the next round the same day neither starts nor writes again");
  reset(); budget = { spent_usd: 13.2, alert_usd: 15 }; env({ SCOUT: "on", SCOUT_MAX_RUNS_PER_ROUND: "5" });
  ok((await scoutRound(deps())).started === 1, "room for one run under the budget line starts exactly one");
  reset(); budget = { spent_usd: 99, alert_usd: 0 }; env({ SCOUT: "on" });
  ok((await scoutRound(deps())).started === 1, "no budget line set (0) does not block the scouts; the run limits still do");

  // ---- hours, owner, dry run, a failed start, tenders
  reset(); clock = Date.parse("2026-11-12T02:00:00Z");
  ok((await scoutRound(deps())).started === 0 && !TABS[SCOUT_SEEN], "outside the scout hours nothing is started or recorded");
  reset(); owner = null;
  const no = await scoutRound(deps());
  ok(no.started === 0 && /no owner/.test(no.note) && !TABS[SCOUT_SEEN], "without an owner chat to report to, nothing is started");
  reset();
  const dry = await scoutRound(deps(), { dry: true });
  ok(dry.started === 0 && /would start 1/.test(dry.note) && starts.length === 0 && !TABS[SCOUT_SEEN], "a dry run decides and reports, records nothing and starts nothing");
  reset(); startFails = true;
  const f1 = await scoutRound(deps());
  ok(f1.started === 0 && decisions().filter((d) => d !== LIMIT).join() === `${PURSUED},skipped: start failed`, "a run that could not be started is recorded as such");
  startFails = false;
  ok((await scoutRound(deps())).started === 1, "and that signal is tried again on a later round");
  reset(); data = { winners: [], tenders: [trow(), trow({ id: "TN-2", new: "" }), trow({ id: "TN-3", stage: "planned" }), trow({ id: "TN-4", days_left: "3" })] };
  const t1 = await scoutRound(deps());
  ok(t1.started === 1 && /^Scout lead, new tender TN-1/.test(starts[0].request) && seenRows().some((r) => r[3] === "TN-4" && r[5] === "skipped: deadline too close") && !seenRows().some((r) => r[3] === "TN-2" || r[3] === "TN-3"), "only tenders the index marks new are signals; one closing too soon is skipped with the reason");
  ok(tenderSignal(trow({ new: "" })) === null && tenderSignal(trow())!.value_usd === 3_000_000 && tenderSignal(trow())!.buyer_awards === 3, "a tender row becomes a signal from its own columns");
  ok(seenRows().find((r) => r[5] === PURSUED && r[6])![7] === "analyst,sourcing", "a tender lead is assigned to the analyst and the sourcing lead");

  // ---- a scout run keeps to its own limits (scripted model)
  let calls = 0; const bodies: { messages: { role: string; content: unknown }[] }[] = [];
  const realFetch = globalThis.fetch;
  const model = (usage: Record<string, number>) => { (globalThis as { fetch: unknown }).fetch = async (_u: string, init: { body: string }) => { calls++; bodies.push(JSON.parse(init.body));
    return { ok: true, json: async () => ({ content: [{ type: "tool_use", id: `u${calls}`, name: "report", input: { text: "עדכון" } }], stop_reason: "tool_use", usage }) }; }; };
  model({ input_tokens: 1000, output_tokens: 100 });
  const lim = await startRun(io, { ...OWNER, request: "Scout lead, test\nbody", origin: "scout", max_turns: 3, max_usd: 5 });
  await step(io, lim.id, 120_000);
  const done = (await loadRun(lim.id))!;
  ok(calls === 3 && done.status === "done" && done.turns === 3, "a run with a 3-step limit makes exactly 3 model calls, far under the normal limit");
  ok(JSON.stringify(bodies[2].messages[bodies[2].messages.length - 1]).includes("This is your last step") && !JSON.stringify(bodies[1].messages).includes("This is your last step"), "its last step is announced to the model so it ends with a summary");
  calls = 0; model({ input_tokens: 400_000, output_tokens: 1000 });
  const cost = await startRun(io, { ...OWNER, request: "Scout lead, cost test", origin: "scout", max_turns: 12, max_usd: 0.3 });
  await step(io, cost.id, 120_000);
  const stopped = (await loadRun(cost.id))!;
  ok(calls === 1 && stopped.status === "done" && /cost limit/.test(stopped.note || "") && sent.some((m) => /תקרת העלות/.test(m.text)), "a run that reaches its cost limit stops before the next model call and tells the owner");
  calls = 0; model({ input_tokens: 1000, output_tokens: 100 });
  const plain = await startRun(io, { ...OWNER, request: "plain request" });
  ok(plain.origin === undefined && plain.max_turns === undefined && plain.max_usd === undefined, "a run the owner starts carries no scout limits: its behaviour is unchanged");
  (globalThis as { fetch: unknown }).fetch = realFetch;

  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
