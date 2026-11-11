// Missions on Sheets (lib/missionstore-sheets.ts) against an in-memory grid: no Google, no network.
import { addTask, createMission, loadMission, type Ctx } from "@/lib/mission";
import { cellsToMissionRow, missionRowToCells, MISSIONS_TAB, SheetsMissionStore } from "@/lib/missionstore-sheets";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
function world() {
  const grid: string[][] = [];
  const store = new SheetsMissionStore({ read: async () => grid.map((r) => [...r]), append: async (cells) => { grid.push(cells.map(String)); } });
  const clock = { t: Date.parse("2026-11-11T08:00:00Z") };
  const ctx: Ctx = { store, now: () => (clock.t += 1000) };
  return { grid, store, ctx };
}
const INPUT = { workspace: "sinder", type: "win_tender" as const, goal: "Win fixture tender T-1", represented_org: "sinder", deal_id: "T-1", cost_budget_usd: 5 };

(async () => {
  ok(MISSIONS_TAB === "Missions", "the tab is called Missions");
  const { grid, store, ctx } = world();
  const a = await createMission(ctx, INPUT), b = await createMission(ctx, INPUT);
  ok(a.ok && b.ok && a.created && !b.created && grid.length === 1, "create is idempotent through the sheet: one row");
  ok(grid[0][1] === "sinder" && grid[0][3] === "mission" && grid[0][5] === "1" && grid[0][6] === "queued" && grid[0].length === 8, "row: workspace in column B, kind, rev, status, 8 columns");
  const id = a.ok ? a.mission.id : "";
  await addTask(ctx, "sinder", id, { idempotency_key: "k1", role: "tender_project", question: "What does the tender require?" });
  const m = await loadMission(ctx, "sinder", id);
  ok(!!m && m.tasks.length === 1 && m.goal === INPUT.goal && m.cost_budget_usd === 5 && m.spent_usd === 0, "a mission and its task survive the round trip");
  const other = await createMission(ctx, { ...INPUT, workspace: "acme", represented_org: "acme", goal: "Acme goal" });
  ok(other.ok && (await store.list("sinder")).length === 1 && (await store.list("acme")).length === 1 && (await store.list("acme"))[0].goal === "Acme goal", "list returns the caller's workspace only");
  ok((await loadMission(ctx, "acme", id)) === null && (await store.load("acme", id)).length === 0, "a mission id from another workspace returns nothing");
  ok((await store.list("")).length === 0 && (await store.list("Not A Workspace")).length === 0, "an empty or unreadable workspace reads nothing (no fallback to the default workspace)");
  grid.push(["2026-11-11", "", id, "mission", id, "9", "cancelled", JSON.stringify({ id, workspace: "", status: "cancelled" })]);
  grid.push(["2026-11-11", "sinder", id, "mission", id, "x", "cancelled", "{}"], ["2026-11-11", "sinder", id, "mission", id, "9", "cancelled", "not json"]);
  ok((await loadMission(ctx, "sinder", id))!.status === "queued", "rows without a workspace, with a bad rev or with broken JSON are ignored");
  let threw = false;
  try { await store.append({ workspace: "", mission_id: "X", kind: "mission", id: "X", rev: 1, time: "t", data: {} }); } catch { threw = true; }
  ok(threw, "a row without a workspace is never written");
  const row = { time: "2026-11-11T08:00:00Z", workspace: "sinder", mission_id: "M", kind: "task" as const, id: "k", rev: 2, data: { status: "running", q: "=HYPERLINK(1)" } };
  ok(JSON.stringify(cellsToMissionRow(missionRowToCells(row).map(String))) === JSON.stringify(row), "cells round trip");
  threw = false;
  try { missionRowToCells({ ...row, data: { big: "x".repeat(50_000) } }); } catch { threw = true; }
  ok(threw, "an oversized row is refused, not cut");
  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
