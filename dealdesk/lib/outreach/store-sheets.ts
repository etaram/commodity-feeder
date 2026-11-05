import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "@/lib/sheets";
import { cellsToRow, emptySnapshot, rowToCells, TAB_KEYS, TABS, type Row, type Snapshot, type Store, type TabKey } from "./store";

// Production store: the six outreach tabs of the engine sheet (created hidden on first append by appendRow).
// One batchGet per load; when a tab does not exist yet the batch fails, so it falls back to one read per tab.
const RANGE = (k: TabKey) => `'${TABS[k]}'!A2:H20000`;

export class SheetsStore implements Store {
  async load(): Promise<Snapshot> {
    if (!sheetsEnabled()) throw new Error("Sheets is not configured");
    const out = emptySnapshot();
    let all: string[][][] | null = null;
    try { all = await readRanges(ENGINE_SHEET, TAB_KEYS.map(RANGE)); } catch { all = null; }
    if (!all) {
      all = [];
      for (const k of TAB_KEYS) all.push((await readRanges(ENGINE_SHEET, [RANGE(k)]).catch(() => null))?.[0] || []);
    }
    TAB_KEYS.forEach((k, i) => { out[k] = (all![i] || []).map(cellsToRow).filter((r): r is Row => !!r); });
    return out;
  }
  async append(tab: TabKey, row: Row): Promise<void> {
    await appendRow(TABS[tab], rowToCells(row));
  }
}

let store: Store | null = null;
export const sheetsStore = () => (store ||= new SheetsStore());
