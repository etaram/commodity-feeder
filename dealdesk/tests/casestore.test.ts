// The case store (lib/casestore.ts): append-only rows where the last row of a case wins, listing newest first, and
// the workspace wall. The Sheets store runs over an in-memory grid; nothing touches Google.
import { AGENT_CASES_TAB, caseProblem, caseToCells, cellsToCase, MAX_JSON, MemoryCaseStore, newCaseId, SheetsCaseStore, CASE_ID, type AgentCase, type CaseStore } from "@/lib/casestore";
import { sheetFor } from "@/lib/sheets";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

const mk = (o: Partial<AgentCase> = {}): AgentCase => ({ id: newCaseId(), created: "2026-11-12T08:00:00.000Z", created_by: "owner@sinder.test", workspace: "sinder", kind: "supplier_rfq",
  target: { company: "Example Mills Ltd", country: "IND" }, brief: { product: "kraft paper 80 gsm", quantity: "not yet known", destination: "not yet known", purpose: "request for quotation" },
  status: "created", reason: "", material: { found: false, note: "", items: [] }, proposal: null, evidence: { verdict: "", issues: [] }, cost: { reserved_usd: 0, actual_usd: null }, decision: null, mission_id: "", updated: "2026-11-12T08:00:00.000Z", ...o });

async function contract(name: string, store: CaseStore, rowCount: () => number) {
  const a = mk({ created: "2026-11-12T08:00:00.000Z" }), b = mk({ created: "2026-11-12T09:00:00.000Z", target: { company: "Second Example GmbH", country: "DEU" } });
  await store.save(a); await store.save(b);
  await store.save({ ...a, status: "running", updated: "2026-11-12T08:00:05.000Z" });
  await store.save({ ...a, status: "waiting_approval", updated: "2026-11-12T08:00:40.000Z", proposal: { to: "sales@example.test", subject: "Enquiry", body: "Hello.", basis: [{ text: "Hello.", rests_on: "courtesy" }] }, evidence: { verdict: "pass", issues: [] } });
  const list = await store.list("sinder");
  ok(rowCount() === 4 && list.length === 2, `${name}: four saves are four rows and two cases`);
  ok(list[0].id === b.id && list[1].id === a.id, `${name}: the list is newest first by creation time`);
  const got = await store.get("sinder", a.id);
  ok(got?.status === "waiting_approval" && got.proposal?.subject === "Enquiry" && got.updated === "2026-11-12T08:00:40.000Z", `${name}: the last row of a case wins`);
  ok((await store.get("sinder", "CASE-000000000000")) === null, `${name}: an unknown id is null`);
  ok((await store.list("acme")).length === 0 && (await store.get("acme", a.id)) === null && (await store.list("")).length === 0, `${name}: another workspace, or none, sees nothing`);
  const c = mk({ workspace: "acme", created: "2026-11-12T10:00:00.000Z" });
  await store.save(c);
  ok((await store.list("acme")).length === 1 && (await store.list("sinder")).length === 2, `${name}: a case belongs to the workspace it was saved in`);
  ok((await store.list("sinder", 1)).length === 1 && (await store.list("sinder", 1))[0].id === b.id, `${name}: the list is cut to n, newest kept`);
  let threw = 0;
  for (const bad of [mk({ id: "x" }), mk({ workspace: "" }), mk({ workspace: "Not Valid" }), mk({ status: "sent" as never }), mk({ target: { company: "", country: "" } })]) await store.save(bad).catch(() => threw++);
  ok(threw === 5 && rowCount() === 5, `${name}: a case without a valid id, workspace, status or company is refused and writes nothing`);
  got!.status = "failed";
  ok((await store.get("sinder", a.id))?.status === "waiting_approval", `${name}: what a read returns is a copy`);
}

(async () => {
  ok(CASE_ID.test(newCaseId()) && newCaseId() !== newCaseId(), "ids are CASE- plus 12 hex characters and differ");
  ok(sheetFor(AGENT_CASES_TAB) === sheetFor("Agent Handoffs") && (() => { process.env.STATE_SHEET_ID = "STATE"; const r = sheetFor(AGENT_CASES_TAB) === "STATE"; delete process.env.STATE_SHEET_ID; return r; })(), "the tab 'Agent Cases' is registered as a state tab");
  const mem = new MemoryCaseStore();
  await contract("memory", mem, () => mem.rows.length);
  const grid: string[][] = [["#"]]; // the marker row a new tab starts with
  await contract("sheets", new SheetsCaseStore({ read: async () => grid.map((r) => [...r]), append: async (c) => { grid.push([...c]); } }), () => grid.length - 1);

  const c = mk();
  const cells = caseToCells(c);
  ok(cells.length === 6 && cells[1] === "sinder" && cells[2] === c.id && cells[3] === "created" && cells[4] === "Example Mills Ltd" && JSON.stringify(cellsToCase(cells)) === JSON.stringify(c), "a case survives the round trip through its row");
  ok(cellsToCase(["#"]) === null && cellsToCase([cells[0], "acme", cells[2], cells[3], cells[4], cells[5]]) === null && cellsToCase([...cells.slice(0, 5), "{broken"]) === null && cellsToCase([cells[0], cells[1], "CASE-AAAAAAAAAAAA", cells[3], cells[4], cells[5]]) === null,
    "the marker row, broken JSON, and a row whose workspace or id column disagrees with its JSON are ignored");
  let big = false;
  try { caseToCells(mk({ material: { found: true, note: "", items: Array.from({ length: 300 }, () => ({ fact: "x".repeat(200), source: "s", date: "2026-11-12" })) } })); } catch (e) { big = /too large/.test(String(e)) && MAX_JSON < 50_000; }
  ok(big, "a case too large for one cell is refused, not cut");
  ok(caseProblem(mk()) === "" && caseProblem(mk({ status: "approved_not_sent" })) === "", "approved_not_sent is a status; there is no 'sent' status in this store");
  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
