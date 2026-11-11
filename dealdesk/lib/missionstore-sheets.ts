// Production store for missions (lib/mission.ts): one append-only tab, "Missions", in the state sheet (the name is
// registered in STATE_TABS, lib/sheets.ts). Nothing is created at import time: appendRow creates the tab, hidden, on
// the first append, and a read of a tab that does not exist yet returns no rows.
// Columns: A time, B workspace, C mission_id, D kind (mission | task), E id, F rev, G status, H data (JSON).
// Every row carries its workspace and every read returns the rows of one workspace only. The match is exact: a row
// with an empty or unreadable workspace belongs to nobody (this tab has no legacy rows to adopt).
import { asWs } from "@/lib/auth";
import { rebuild, type Mission, type MissionRow, type MissionStore } from "@/lib/mission";
import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "@/lib/sheets";

export const MISSIONS_TAB = "Missions";
const RANGE = `'${MISSIONS_TAB}'!A2:H20000`;
export const MAX_JSON = 45_000;

export function missionRowToCells(r: MissionRow): (string | number)[] {
  const json = JSON.stringify(r.data);
  if (json.length > MAX_JSON) throw new Error(`mission row ${r.id} is too large to store (${json.length} chars)`);
  return [r.time, asWs(r.workspace), r.mission_id, r.kind, r.id, r.rev, String((r.data as { status?: unknown }).status ?? ""), json];
}
export function cellsToMissionRow(c: string[] | undefined): MissionRow | null {
  if (!c || !c[1] || !c[2] || !c[4] || (c[3] !== "mission" && c[3] !== "task")) return null;
  const rev = Number(c[5]);
  if (!Number.isInteger(rev) || rev < 1) return null;
  let data: Record<string, unknown>;
  try { data = JSON.parse(c[7] || ""); } catch { return null; }
  if (!data || typeof data !== "object" || Array.isArray(data)) return null;
  return { time: c[0] || "", workspace: c[1], mission_id: c[2], kind: c[3], id: c[4], rev, data };
}

// The two calls the store makes, injected so the tests run without Google.
export type MissionIo = { read: () => Promise<string[][]>; append: (cells: (string | number)[]) => Promise<void> };
const sheetsIo: MissionIo = {
  async read() {
    if (!sheetsEnabled()) throw new Error("Sheets is not configured");
    try { return (await readRanges(ENGINE_SHEET, [RANGE]))?.[0] || []; }
    catch (e) { if (String(e).includes("Unable to parse range")) return []; throw e; } // the tab is not created yet
  },
  async append(cells) { await appendRow(MISSIONS_TAB, cells); },
};

export class SheetsMissionStore implements MissionStore {
  constructor(private io: MissionIo = sheetsIo) {}
  /** Every stored row of one workspace. */
  async rows(workspace: string): Promise<MissionRow[]> {
    const ws = asWs(workspace);
    if (!workspace || ws !== workspace) return []; // an unreadable workspace never falls back to the default one
    return (await this.io.read()).map(cellsToMissionRow).filter((r): r is MissionRow => !!r && r.workspace === ws);
  }
  async load(workspace: string, missionId: string): Promise<MissionRow[]> {
    return (await this.rows(workspace)).filter((r) => r.mission_id === missionId);
  }
  async append(row: MissionRow): Promise<void> {
    if (!row.workspace || asWs(row.workspace) !== row.workspace) throw new Error("mission row has no valid workspace");
    await this.io.append(missionRowToCells(row));
  }
  /** The missions of one workspace, newest first. */
  async list(workspace: string): Promise<Mission[]> {
    const by = new Map<string, MissionRow[]>();
    for (const r of await this.rows(workspace)) by.set(r.mission_id, [...(by.get(r.mission_id) || []), r]);
    return [...by.values()].map(rebuild).filter((m): m is Mission => !!m).sort((a, b) => (a.created_at < b.created_at ? 1 : a.created_at > b.created_at ? -1 : 0));
  }
}

let store: SheetsMissionStore | null = null;
export const sheetsMissionStore = () => (store ||= new SheetsMissionStore());
