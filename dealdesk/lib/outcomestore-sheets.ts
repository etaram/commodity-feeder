// Production store for the outcome ledger (lib/outcomes.ts): one append-only tab, "Outcomes", in the state sheet (the
// name is registered in STATE_TABS, lib/sheets.ts). Same pattern as lib/missionstore-sheets.ts: nothing is created at
// import time, appendRow creates the tab, hidden, on the first append, and a read of a missing tab returns no rows.
// Columns: A at (when it happened), B workspace, C case_id, D route_id, E type, F proof (kind:id), G data (JSON, the
// whole event). The JSON is what is read back; columns A to F are for a person reading the sheet. A row whose JSON is
// broken, or whose event the ledger's own validation refuses, is ignored. The ledger (createLedger) does the
// workspace filtering: this store returns every valid row, as the in-memory store does.
import { eventProblems, type OutcomeEvent, type OutcomeStore } from "@/lib/outcomes";
import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "@/lib/sheets";

export const OUTCOMES_TAB = "Outcomes";
const RANGE = `'${OUTCOMES_TAB}'!A1:G20000`;
export const MAX_JSON = 8_000;

const canon = (e: OutcomeEvent): OutcomeEvent => ({ type: e.type, case_id: e.case_id, route_id: e.route_id, workspace: e.workspace, at: e.at, actor: e.actor, counterparty: e.counterparty,
  proof: { kind: e.proof.kind, id: e.proof.id }, rights_scope: e.rights_scope, model_version: e.model_version, display_rank: e.display_rank, reason: e.reason ?? null });

export function outcomeToCells(e: OutcomeEvent): (string | number)[] {
  const probs = eventProblems(e);
  if (probs.length) throw new Error(`outcome event rejected: ${probs.join("; ")}`);
  const json = JSON.stringify(canon(e));
  if (json.length > MAX_JSON) throw new Error(`outcome event is too large to store (${json.length} chars)`);
  return [e.at, e.workspace, e.case_id, e.route_id, e.type, `${e.proof.kind}:${e.proof.id}`, json];
}
export function cellsToOutcome(c: string[] | undefined): OutcomeEvent | null {
  if (!c || !c[1] || !c[6]) return null;
  let e: OutcomeEvent;
  try { e = JSON.parse(c[6]); } catch { return null; }
  if (!e || typeof e !== "object" || Array.isArray(e) || eventProblems(e).length) return null;
  if (e.workspace !== c[1]) return null; // the workspace column and the event must agree: an edited cell never moves a row
  return canon(e);
}

// The two calls the store makes, injected so the tests run without Google.
export type OutcomeIo = { read: () => Promise<string[][]>; append: (cells: (string | number)[]) => Promise<void> };
const sheetsIo: OutcomeIo = {
  async read() {
    if (!sheetsEnabled()) throw new Error("Sheets is not configured");
    try { return (await readRanges(ENGINE_SHEET, [RANGE]))?.[0] || []; }
    catch (e) { if (String(e).includes("Unable to parse range")) return []; throw e; } // the tab is not created yet
  },
  async append(cells) { await appendRow(OUTCOMES_TAB, cells); },
};

export class SheetsOutcomeStore implements OutcomeStore {
  constructor(private io: OutcomeIo = sheetsIo) {}
  async append(e: OutcomeEvent): Promise<void> { await this.io.append(outcomeToCells(e)); }
  async all(): Promise<OutcomeEvent[]> { return (await this.io.read()).map(cellsToOutcome).filter((e): e is OutcomeEvent => !!e); }
}

let store: SheetsOutcomeStore | null = null;
export const sheetsOutcomeStore = () => (store ||= new SheetsOutcomeStore());
