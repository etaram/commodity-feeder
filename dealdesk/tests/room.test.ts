// The operations room's shaping (lib/room.ts) from fixture rows in the stored formats: what each team member is doing,
// the feed, today's hunt, what waits for the owner, and the 7-day counters. Pure. All names are made up.
import { describeTool, readApprovals, readRuns, shapeRoom, STALE_MS, type RoomInput } from "@/lib/room";
import { seenToCells, PURSUED, LIMIT } from "@/lib/scout";
import { TEAM } from "@/lib/team";
import type { Mission } from "@/lib/mission";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

const NOW = Date.parse("2026-11-12T10:00:00Z");
const at = (minAgo: number) => new Date(NOW - minAgo * 60_000).toISOString();
const use = (id: string, name: string, input: Record<string, unknown> = {}) => ({ type: "tool_use", id, name, input });
const runRow = (id: string, minAgo: number, status: string, blocks: unknown[], o: Record<string, unknown> = {}) =>
  [id, at(minAgo), "C1", "o@x.test", status, "3", JSON.stringify({ id, ws: "sinder", status, request: `Request of ${id}\nmore`, deal_id: `AGENT-${id}`, turns: 3, usd: 0.25, started: at(Number(o.startedAgo ?? minAgo + 5)),
    msgs: [{ role: "user", content: "x" }, { role: "assistant", content: blocks }], ...o })];
const appr = (id: string, run: string, minAgo: number, status: string, m: Record<string, unknown> = {}) => [id, run, "C1", at(minAgo), status, JSON.stringify({ from_role: "relations_asia", to_name: "Example Mills Co", subject: "RFQ", why: "supported match", ...m })];
const seen = (id: string, minAgo: number, decision: string, o: Record<string, unknown> = {}) => seenToCells({ time: at(minAgo), ws: "sinder", kind: "winner", id, score: 61, decision, run_id: "", assignees: ["relations_africa", "analyst"], label: `Example Contractor: lot ${id}`, reasons: ["value USD 10.0M: +16"], deal_id: "", ...o }).map(String);
const base = (o: Partial<RoomInput> = {}): RoomInput => ({ ws: "sinder", now: NOW, runs: [], approvals: [], seen: [], guard: [], missions: [], scoutOn: false, ...o });
const mem = (v: ReturnType<typeof shapeRoom>, id: string) => v.team.find((m) => m.id === id)!;

// ---- nothing stored
const empty = shapeRoom(base());
ok(empty.team.length === TEAM.length && empty.team.every((m) => m.state === "idle" && m.now === "" && m.last_active === "" && m.today === 0), "no stored rows: every member of the roster is shown idle, with no invented activity");
ok(empty.feed.length === 0 && empty.waiting.length === 0 && empty.hunt.looked === 0 && empty.running === 0, "no stored rows: empty feed, nothing waiting, no hunt, no run in progress");
ok(empty.counters.runs === 0 && empty.counters.sent === 0 && empty.counters.replies === null && /not read from the mailbox yet/.test(empty.counters.replies_note), "counters are zero and replies say they are not read from the mailbox yet");
ok(empty.team.map((m) => m.name).join() === TEAM.map((m) => m.name).join() && mem(empty, "relations_africa").region === "אפריקה", "cards follow the roster order with the member's region");

// ---- a run in progress
const live = shapeRoom(base({ runs: [
  runRow("AG1", 6, "running", [use("a", "search_tenders", { words: "pumps" })]),
  runRow("AG1", 2, "running", [use("a", "search_tenders", { words: "pumps" }), use("b", "search_suppliers", { product: "centrifugal pumps", origin_country: "IND" })])] }));
ok(live.running === 1 && mem(live, "sourcing").state === "working" && /חיפוש ספקים במאגר: centrifugal pumps \(IND\)/.test(mem(live, "sourcing").now) && mem(live, "sourcing").deal_id === "AGENT-AG1", "a running run puts the member who owns its last tool at work, with what the tool did");
ok(mem(live, "analyst").state === "idle" && mem(live, "analyst").last_active === at(6) && mem(live, "analyst").today === 1, "a member whose tool ran earlier in the run is not shown as working now, but keeps a last-activity time");
ok(mem(live, "evidence").state === "idle" && mem(live, "economics").state === "idle", "members with no row behind them stay idle");
const f1 = live.feed.map((f) => `${f.kind}@${f.at}`);
ok(live.feed.length === 3 && live.feed[0].kind === "tool" && live.feed[0].at === at(2) && f1.includes(`tool@${at(6)}`) && live.feed[2].kind === "start", "the feed is newest first; each tool call appears once, at the time of the step that first saved it");
ok(live.feed[0].who === "Daniel Okafor" && live.feed[0].deal_id === "AGENT-AG1" && /Request of AG1$/.test(live.feed[2].text), "a feed line names the member by rule, links the deal, and a run is titled by the first line of its request");

// ---- a run that stopped chaining
const stale = shapeRoom(base({ runs: [runRow("AG2", STALE_MS / 60_000 + 5, "running", [use("a", "deal_economics")])] }));
ok(stale.running === 0 && mem(stale, "economics").state === "stalled" && /לא התקדמה/.test(mem(stale, "economics").now), "a run marked running with no saved step for 15 minutes is shown as stalled, not as working");

// ---- waiting for the owner
const wait = shapeRoom(base({
  runs: [runRow("AG3", 30, "done", [use("a", "propose_message", { from_role: "relations_asia", to_name: "Example Mills Co" }), use("z", "finish", { summary: "נמצא ספק אחד" })]),
    runRow("AG4", 20, "waiting", [use("q0", "tender_routes", { tender_id: "T9" }), use("q", "ask_owner", { question: "כמה טון?" })])],
  approvals: [appr("M1", "AG3", 31, "pending"), appr("M2", "AG3", 29, "pending", { to_name: "Example Foods Ltd", unverified: "address found on the web, not verified" }), appr("M2", "AG3", 25, "rejected"),
    appr("M9", "AG-OTHER", 10, "pending")] }));
ok(wait.waiting.length === 1 && wait.waiting[0].id === "M1" && wait.waiting[0].by === "Mei Lin Zhang" && wait.waiting[0].deal_id === "AGENT-AG3" && wait.waiting[0].to_name === "Example Mills Co", "pending messages wait for the owner, with who prepared them and the deal to open");
ok(!wait.waiting.some((p) => p.id === "M9"), "a message whose run is not in this workspace is not shown");
ok(mem(wait, "relations_asia").state === "waiting" && /ממתינה לאישור הבעלים: Example Mills Co/.test(mem(wait, "relations_asia").now), "the member who signed a pending message is waiting for the owner");
ok(mem(wait, "analyst").state === "waiting" && /כמה טון/.test(mem(wait, "analyst").now), "a run paused on a question shows its member waiting, with the question");
ok(wait.feed.some((f) => f.kind === "proposed" && /Example Mills Co/.test(f.text)) && wait.feed.some((f) => f.kind === "rejected" && /Example Foods Ltd/.test(f.text)) && wait.feed.some((f) => f.kind === "question") && wait.feed.some((f) => f.kind === "finish" && /נמצא ספק אחד/.test(f.text)), "feed: message proposed, owner rejected, question asked, run finished with its summary");
ok(wait.feed.filter((f) => /Example Mills Co/.test(f.text)).length === 1, "a proposed message appears once (from the approvals tab, not also as a tool call)");
ok(wait.counters.proposed === 2 && wait.counters.rejected === 1 && wait.counters.approved === 0, "counters: two messages proposed, one rejected, none approved");

// ---- approved and sent, 7-day window
const week = shapeRoom(base({
  runs: [runRow("AG5", 60, "done", [use("a", "finish", { summary: "done" })]), runRow("AG6", 60 * 24 * 9, "done", [use("a", "finish", { summary: "old" })]), runRow("AG7", 50, "done", [], { ws: "acme" })],
  approvals: [appr("M3", "AG5", 58, "pending"), appr("M3", "AG5", 55, "sending"), appr("M3", "AG5", 54, "sent"), appr("M4", "AG5", 57, "pending"), appr("M4", "AG5", 50, "send_failed"), appr("M5", "AG6", 60 * 24 * 9, "pending")],
  guard: [[at(55), "sinder", "approval:M3", "reserved"], [at(54), "sinder", "approval:M3", "sent"], [at(60 * 24 * 9), "sinder", "k-old", "sent"], [at(40), "acme", "k", "sent"], [at(50), "sinder", "approval:M4", "send_failed"]] }));
ok(week.counters.runs === 1 && week.counters.proposed === 2 && week.counters.approved === 2 && week.counters.sent === 1 && week.counters.est_usd === 0.25, "7-day counters count this workspace's rows inside the window only; sent comes from the Send Guard rows marked sent");
ok(week.feed.some((f) => f.kind === "approved" && f.at === at(55)) && week.feed.some((f) => f.kind === "sent" && f.at === at(54)) && week.feed.some((f) => f.kind === "send_problem" && /לא נשלחה/.test(f.text)), "feed: owner approved, message sent, and an approved message that did not leave");
ok(week.waiting.length === 1 && week.waiting[0].id === "M5" && !week.feed.some((f) => f.run_id === "AG7"), "an old pending message still waits; another workspace's run never appears");
ok(mem(week, "relations_asia").state === "waiting" && TEAM.filter((m) => m.id !== "relations_asia").every((m) => mem(week, m.id).state === "idle"), "a finished run with no tool of theirs leaves members idle");

// ---- done today, scouts, hunt
const hunt = shapeRoom(base({ scoutOn: true,
  runs: [runRow("AG8", 3, "running", [use("a", "company_footprint", { company: "Example Contractor" })], { origin: "scout" }), runRow("AG9", 90, "done", [use("a", "logistics_options", { destination_country: "KEN" }), use("b", "finish", { summary: "ok" })])],
  seen: [seen("S1", 12, PURSUED), seen("S1", 11, PURSUED, { run_id: "AG8", deal_id: "AGENT-AG8" }), seen("S2", 11, LIMIT, { reasons: ["daily run limit reached (3 a day)"] }), seen("S3", 11, "skipped: outside focus"),
    seen("S4", 60 * 30, PURSUED, { run_id: "AG0" }), seenToCells({ time: at(5), ws: "acme", kind: "winner", id: "S9", score: 90, decision: PURSUED, run_id: "", assignees: [], label: "other", reasons: [], deal_id: "" }).map(String)] }));
ok(hunt.hunt.looked === 3 && hunt.hunt.pursued === 1 && hunt.hunt.skipped.length === 2 && hunt.hunt.skipped.some((s) => s.reason === LIMIT && s.n === 1), "today's hunt: signals looked at, how many pursued, and the skipped ones by reason");
ok(hunt.hunt.items[0].assignees.join() === "Grace Mwangi,Claire Bennett" && hunt.hunt.items.find((h) => h.run_id === "AG8")!.deal_id === "AGENT-AG8" && hunt.hunt.items.every((h) => h.label !== "other"), "a hunt item carries its score, reasons, assignees and deal; another workspace's and yesterday's are left out");
ok(mem(hunt, "relations_africa").state === "working" && /מוביל\/ה ליד של סקאוט/.test(mem(hunt, "relations_africa").now) && mem(hunt, "analyst").state === "working" && /רקורד חוזים ציבוריים/.test(mem(hunt, "analyst").now), "a scout run puts its assigned lead at work, and the analyst while her tool is the last one used");
ok(mem(hunt, "logistics").state === "done_today" && /סיים\/ה היום/.test(mem(hunt, "logistics").now), "a member whose tool ran in a run finished today is shown as done today");
ok(hunt.counters.scout_runs === 1 && hunt.feed.some((f) => f.kind === "start" && /סקאוט פתח ריצה/.test(f.text) && f.who === "Grace Mwangi") && hunt.feed.some((f) => f.kind === "scout" && /outside focus/.test(f.text)), "feed and counters mark the scouts' runs and their skips");
ok(hunt.scout_on === true && empty.scout_on === false, "the view says whether the scouts are on");

// ---- missions, errors, parsing
const mission = (status: string, role: string, tstatus: string): Mission => ({ id: "MS1", workspace: "sinder", type: "tender_bid", goal: "g", represented_org: "sinder", deal_id: "D1", cost_budget_usd: 5, spent_usd: 0, allowed_tools: [], stop_rules: [], status,
  next_decision: "", created_at: at(40), updated_at: at(4), tasks: [{ idempotency_key: "MS1:read", role, question: "List the eligibility conditions", depends_on: [], attempt: 1, max_attempts: 2, cost_reservation_usd: 1, status: tstatus, output: null, reviewer_result: null, last_error: "", seq: 0 }] } as unknown as Mission);
const ms1 = shapeRoom(base({ missions: [mission("running", "tender_project", "running")] }));
ok(mem(ms1, "analyst").state === "working" && /משימה \(MS1\): List the eligibility/.test(mem(ms1, "analyst").now), "a running mission task puts its role's single persona at work");
const ms2 = shapeRoom(base({ missions: [mission("running", "regional_relations", "running"), mission("running", "red_team", "running")] }));
ok(ms2.team.every((m) => m.state === "idle"), "a mission role shared by several members, or with no persona, is attributed to nobody");
ok(shapeRoom(base({ errors: ["Agent Runs: could not be read"] })).notes.join() === "Agent Runs: could not be read", "a tab that could not be read is named on the screen");
ok(readRuns([["AG1", at(1), "C", "e", "running", "1", "{broken"], ["#"], []]).length === 0 && readApprovals([["M1", "AG1", "C", at(1), "pending", "not json"]])[0].to_name === "", "cut or unreadable rows are skipped without failing the screen");
const compact = readRuns([runRow("AG1", 9, "running", [use("a", "search_tenders"), use("b", "tender_routes")]), runRow("AG1", 4, "running", [use("b", "tender_routes"), use("c", "deal_economics")])])[0];
ok(compact.tools.map((t) => t.name).join() === "search_tenders,tender_routes,deal_economics" && compact.tools[2].at === at(4), "tool calls dropped from a later, shortened state are kept from the earlier rows");
ok(/דרכי כניסה למכרז T1/.test(describeTool("tender_routes", { tender_id: "T1" })) && /כלי: odd_tool/.test(describeTool("odd_tool")) && !/undefined/.test(describeTool("search_suppliers")), "every tool has a one-line description, and an unknown tool is named as it is");

if (fail) { console.log(`${fail} failed`); process.exit(1); }
