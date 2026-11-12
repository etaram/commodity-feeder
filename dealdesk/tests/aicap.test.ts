// Monthly AI cap as a hard ceiling (lib/anthropic.ts reserveCall): fail closed when the ledger cannot be read, no
// exempt job, the worst case of each call reserved before it is sent (parallel calls included), the reservation
// replaced by the actual cost on completion and released on an error, and multi-turn calls reserved per turn.
// Built with the in-memory sheet (tests/build-agent-test.mjs); no request leaves the process.
import { TABS } from "./mocks/sheets";
import { defaultCap, CAP_REFUSAL, CAP_UNKNOWN, checkMonthlyCap, claude, estimateCost, modelTurn, reservedNow, spentThisMonth, worstCaseCost, budgetState } from "@/lib/anthropic";
import { spendReport } from "@/lib/spend";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const near = (a: number | null, b: number) => a !== null && Math.abs(a - b) < 1e-9;
process.env.ANTHROPIC_API_KEY = "test-key";

// model stand-in: every request is recorded; the next answers are queued; a gate can hold answers back
type Ans = { status?: number; usage?: Record<string, number>; stop?: string; throws?: boolean };
const sent: Record<string, unknown>[] = [];
let queue: Ans[] = [], gate: Promise<void> | null = null;
(globalThis as { fetch: unknown }).fetch = async (_u: string, init: { body: string }) => {
  sent.push(JSON.parse(init.body));
  const a = queue.shift() || {};
  if (gate) await gate;
  if (a.throws) throw new Error("network down");
  return { ok: (a.status || 200) < 300, status: a.status || 200, json: async () => (a.status && a.status >= 300 ? { error: { message: "overloaded" } } : { content: [{ type: "text", text: "fine" }], stop_reason: a.stop || "end_turn", usage: a.usage || { input_tokens: 100, output_tokens: 10 } }) };
};
const errOf = async (p: Promise<unknown>) => { try { await p; return ""; } catch (e) { return String((e as Error).message || e); } };
const tick = () => new Promise((r) => setTimeout(r, 5));
const now = () => new Date().toISOString();
const small = { max_tokens: 50, messages: [{ role: "user", content: "hi" }] };

(async () => {
  // 1. the ledger cannot be read (never read before on this instance): every job is refused, nothing is sent
  Object.defineProperty(TABS, "AI Usage", { configurable: true, get() { throw new Error("sheet unavailable"); } });
  ok((await spentThisMonth(true)) === null, "unreadable ledger: this month's spend is unknown, not 0");
  for (const job of ["brief", "health", "deal agent"]) {
    const e = await errOf(claude(small, { job }));
    ok(e.startsWith(CAP_UNKNOWN), `unreadable ledger: '${job}' is refused with a clear reason`);
  }
  ok((await errOf(checkMonthlyCap("telegram"))).startsWith(CAP_UNKNOWN), "unreadable ledger: the Telegram/deal-agent check refuses too");
  ok(sent.length === 0 && reservedNow() === 0, "unreadable ledger: no request was sent and nothing stays reserved");
  ok((await budgetState()).month_stopped === true && (await budgetState()).month_unknown === true, "budget state reports the AI as stopped (spend unknown)");

  // 2. readable again: near the cap, a call whose worst case would cross the cap is refused while a smaller one passes
  Object.defineProperty(TABS, "AI Usage", { configurable: true, writable: true, enumerable: true, value: [["time", "job", "ws", "model", "in", "out", "cache", "searches", "usd"], [now(), "brief", "", "m", 0, 0, 0, 0, 29.9]] });
  process.env.ANTHROPIC_MONTHLY_CAP_USD = "30";
  ok(near(await spentThisMonth(true), 29.9), "readable ledger: this month's spend is read");
  const big = { max_tokens: 64000, messages: [{ role: "user", content: "write a long report" }] };
  ok(worstCaseCost(big) > 0.1 && worstCaseCost(small) < 0.01, "worst case = input estimate + max_tokens at list price");
  const n1 = sent.length;
  const eb = await errOf(claude(big, { job: "brief" }));
  ok(eb.startsWith(CAP_REFUSAL) && /could cost up to/.test(eb) && sent.length === n1, "near the cap: a call whose worst case would cross the cap is refused before sending");
  const es = await errOf(claude(small, { job: "brief" }));
  ok(es === "" && sent.length === n1 + 1, "near the cap: a smaller call that fits passes");
  const eh = await errOf(claude({ max_tokens: 64000, messages: [{ role: "user", content: "Reply OK" }] }, { job: "health" }));
  ok(eh.startsWith(CAP_REFUSAL), "no exemption: the health job is refused over the cap like any other");

  // 3. a short last-good value covers one failed read, for at most a few minutes
  Object.defineProperty(TABS, "AI Usage", { configurable: true, writable: true, enumerable: true, value: [[now(), "brief", "", "m", 0, 0, 0, 0, 1]] });
  process.env.ANTHROPIC_MONTHLY_CAP_USD = "10";
  ok(near(await spentThisMonth(true), 1), "fresh reading: $1 spent");
  const good = TABS["AI Usage"];
  Object.defineProperty(TABS, "AI Usage", { configurable: true, get() { throw new Error("slow read"); } });
  ok(near(await spentThisMonth(true), 1), "a failed read right after a good one uses the last good value");
  const realNow = Date.now;
  Date.now = () => realNow() + 6 * 60_000;
  ok((await spentThisMonth(true)) === null && (await errOf(claude(small, { job: "brief" }))).startsWith(CAP_UNKNOWN), "after 6 minutes without a good read the spend is unknown and calls are refused");
  Date.now = realNow;
  Object.defineProperty(TABS, "AI Usage", { configurable: true, writable: true, enumerable: true, value: good });
  await spentThisMonth(true);

  // 4. concurrent calls: N parallel reservations cannot together exceed the cap
  const w = worstCaseCost({ model: "claude-haiku-5-5", ...small });
  process.env.ANTHROPIC_MONTHLY_CAP_USD = String(1 + 3.5 * w);    // room for exactly 3 worst cases
  let open!: () => void; gate = new Promise<void>((r) => { open = r; });
  queue = Array.from({ length: 10 }, () => ({ usage: { input_tokens: 10, output_tokens: 2 } }));
  const n2 = sent.length;
  const par = Array.from({ length: 10 }, () => errOf(claude(small, { job: "brief" })));
  await tick();
  ok(sent.length - n2 === 3 && near(reservedNow(), 3 * w), "10 parallel calls: only 3 are sent, their worst cases are held");
  ok(1 + reservedNow() <= Number(process.env.ANTHROPIC_MONTHLY_CAP_USD), "spent + reserved never passes the cap");
  const bs = await budgetState();
  ok(bs.month_reserved_usd > 0 && bs.month_inflight === 3, "budget state shows the reserved in-flight amount");
  const rep = spendReport({ now: Date.now(), env: process.env as Record<string, string | undefined>, ai: { rows: TABS["AI Usage"].map((r: (string | number)[]) => r.map(String)) }, agent: null, fixed: [], aiReserved: reservedNow() });
  const an = rep.services.find((s) => s.id === "anthropic")!;
  ok((an.reserved_usd || 0) > 0 && /reserved for calls in progress/.test(an.detail || ""), "spending screen line shows the reserved in-flight amount");
  open(); gate = null;
  const res = await Promise.all(par);
  ok(res.filter((e) => e === "").length === 3 && res.filter((e) => e.startsWith(CAP_REFUSAL)).length === 7, "the other 7 were refused with the cap reason");

  // 5. actual cost replaces the reservation (counted once, also after the ledger row lands and is re-read)
  const actual = 3 * estimateCost({ input_tokens: 10, output_tokens: 2 });
  ok(reservedNow() === 0 && near(await spentThisMonth(), 1 + actual), "on completion the reservations are replaced by the actual cost");
  await tick();
  ok(near(await spentThisMonth(true), 1 + actual), "after the ledger rows land and are re-read, the cost is counted once");

  // 6. reservation released on error (provider error, network error)
  process.env.ANTHROPIC_MONTHLY_CAP_USD = "30";
  const before = await spentThisMonth(true);
  queue = [{ status: 529 }];
  ok(/Anthropic 529/.test(await errOf(claude(small, { job: "brief" }))) && reservedNow() === 0, "provider error: the reservation is released");
  await tick();
  ok(near(await spentThisMonth(true), before!), "a refused provider answer (HTTP error) adds nothing to this month's spend");
  const worstSmall = worstCaseCost({ model: "m", ...small });
  queue = [{ throws: true }];
  ok(/network down/.test(await errOf(modelTurn("deal agent", "", { model: "m", ...small }))) && reservedNow() === 0, "network error in a tool-loop turn: no longer a live reservation");
  await tick();
  ok(near(await spentThisMonth(true), before! + worstSmall), "an ambiguous failure (network/timeout) keeps its worst case counted for the month: a missing usage row is not proof of zero charge");

  // 7. multi-turn: each turn reserves through the same function; a continuation that would cross the cap is not sent
  const cur = (await spentThisMonth(true))!;
  const wt = worstCaseCost({ model: "m", ...small });
  process.env.ANTHROPIC_MONTHLY_CAP_USD = String(cur + 0.5 + 0.5 * wt);   // the first turn fits; after its $0.5 cost the second does not
  queue = [{ stop: "max_tokens", usage: { input_tokens: 0, output_tokens: 100000 } }];   // $0.5 actual
  const n3 = sent.length;
  const ec = await errOf(claude(small, { job: "brief" }));
  ok(ec.startsWith(CAP_REFUSAL) && sent.length === n3 + 1 && reservedNow() === 0, "continuation turn: reserved per turn, refused before sending once the cap would be passed");
  queue = [{ usage: { input_tokens: 10, output_tokens: 1 } }];
  process.env.ANTHROPIC_MONTHLY_CAP_USD = "1000";
  const mt = await modelTurn("telegram", "", { model: "m", ...small });
  await tick();
  ok(mt.ok && reservedNow() === 0 && TABS["AI Usage"].some((r: (string | number)[]) => r[1] === "telegram"), "a tool-loop turn (Telegram, deal agent) is reserved, metered and written to the ledger");
  ok(defaultCap(new Date("2026-11-20T00:00:00Z")) === 50 && defaultCap(new Date("2026-12-01T00:00:00Z")) === 30 && defaultCap(new Date("2026-10-31T23:00:00Z")) === 30, "default cap: USD 50 in November 2026 (setup month), USD 30 otherwise");
  delete process.env.ANTHROPIC_MONTHLY_CAP_USD;
  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})();
