// Cases of the role pipeline (lib/pipeline.ts) as the owner sees them: who we want to write to, what we would ask,
// where the case stands, the proposed message when there is one, and what the owner decided. One append-only tab,
// 'Agent Cases', in the state sheet (registered in STATE_TABS, lib/sheets.ts). Same pattern as
// lib/missionstore-sheets.ts: nothing is created at import time, appendRow creates the tab on the first append, a read
// of a tab that does not exist yet returns no rows. Every save appends the whole case; the last row of an id wins.
// Columns: A updated, B workspace, C id, D status, E company, F data (JSON, the whole case). Columns A to E are for a
// person reading the sheet; F is what is read back. A row belongs to exactly one workspace: the match is exact, and a
// row whose workspace column and JSON disagree is ignored, so an edited cell never moves a case.
//
// Nothing here sends anything. 'approved_not_sent' means what it says: the owner pressed Approve and no message left.
import { randomUUID } from "crypto";
import { asWs } from "@/lib/auth";
import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "@/lib/sheets";

export const AGENT_CASES_TAB = "Agent Cases";
// created: stored, material not gathered yet.   no_material: the company is not in the system's data; no model ran.
// pipeline_off: material gathered, AGENT_PIPELINE is off.   running: handed to the roles; a case that stays here did
// not finish inside its request and shows its last recorded hand-off.   The next six are lib/pipeline.ts CaseStatus.
// rejected / approved_not_sent: the owner's decision on a proposal.
export const CASE_STATUSES = ["created", "no_material", "pipeline_off", "running", "waiting_approval", "no_message", "needs_owner", "blocked", "budget_stopped", "failed", "off", "rejected", "approved_not_sent"] as const;
export type AgentCaseStatus = (typeof CASE_STATUSES)[number];
export type MaterialItem = { fact: string; source: string; date: string };
export type AgentCase = {
  id: string; created: string; created_by: string; workspace: string; kind: "supplier_rfq";
  target: { company: string; country: string; website?: string; contact_email?: string };
  brief: { product: string; quantity: string; destination: string; purpose: string };
  status: AgentCaseStatus; reason: string;
  /** what the system's own data holds about the target, gathered without a model (lib/casematerial.ts) */
  material: { found: boolean; note: string; items: MaterialItem[] };
  /** basis: one entry per sentence of the body, with what that sentence rests on */
  proposal: { to: string; subject: string; body: string; basis: { text: string; rests_on: string }[] } | null;
  evidence: { verdict: "" | "pass" | "send_back" | "block"; issues: string[] };
  cost: { reserved_usd: number; actual_usd: number | null };
  decision: { decision: "reject" | "approve"; by: string; at: string } | null;
  mission_id: string; updated: string;
};
export interface CaseStore {
  save(c: AgentCase): Promise<void>;
  get(workspace: string, id: string): Promise<AgentCase | null>;
  /** newest first, at most n */
  list(workspace: string, n?: number): Promise<AgentCase[]>;
}

export const newCaseId = () => `CASE-${randomUUID().replace(/-/g, "").slice(0, 12).toUpperCase()}`;
export const CASE_ID = /^CASE-[0-9A-F]{12}$/;
export const MAX_JSON = 45_000; // a cell holds 50,000 characters

/** Why a case may not be stored; "" when it may. */
export function caseProblem(c: AgentCase): string {
  if (!c || !CASE_ID.test(String(c.id || ""))) return "a case needs an id";
  if (!c.workspace || asWs(c.workspace) !== c.workspace) return "a case needs a valid workspace";
  if (!(CASE_STATUSES as readonly string[]).includes(c.status)) return `unknown status ${String(c.status)}`;
  if (!c.target?.company) return "a case needs a target company";
  return "";
}
export function caseToCells(c: AgentCase): string[] {
  const p = caseProblem(c);
  if (p) throw new Error(p);
  const json = JSON.stringify(c);
  if (json.length > MAX_JSON) throw new Error(`case ${c.id} is too large to store (${json.length} chars)`);
  return [c.updated, c.workspace, c.id, c.status, c.target.company.slice(0, 160), json];
}
export function cellsToCase(r: string[] | undefined): AgentCase | null {
  if (!r || !r[1] || !r[2] || !r[5]) return null; // the marker row and blank lines
  let c: AgentCase;
  try { c = JSON.parse(r[5]); } catch { return null; }
  if (!c || typeof c !== "object" || Array.isArray(c) || caseProblem(c)) return null;
  return c.workspace === r[1] && c.id === r[2] ? c : null;
}

/** Latest row per id, newest case first (by creation time; the id breaks a tie so the order is stable). */
function latest(rows: AgentCase[]): AgentCase[] {
  const by = new Map<string, AgentCase>();
  for (const c of rows) by.set(c.id, c); // rows come in append order: a later row replaces an earlier one
  return [...by.values()].sort((a, b) => (a.created < b.created ? 1 : a.created > b.created ? -1 : a.id < b.id ? 1 : -1));
}
const copy = (c: AgentCase): AgentCase => JSON.parse(JSON.stringify(c));

export class MemoryCaseStore implements CaseStore {
  rows: AgentCase[] = [];
  async save(c: AgentCase) { const p = caseProblem(c); if (p) throw new Error(p); this.rows.push(copy(c)); }
  async get(workspace: string, id: string) { return (await this.list(workspace, Infinity)).find((c) => c.id === id) || null; }
  async list(workspace: string, n = 50) { return latest(this.rows.filter((c) => !!workspace && c.workspace === workspace)).slice(0, n).map(copy); }
}

// The two calls the Sheets store makes, injected so the tests run without Google.
export type CaseIo = { read: () => Promise<string[][]>; append: (cells: string[]) => Promise<void> };
const sheetsIo: CaseIo = {
  async read() {
    if (!sheetsEnabled()) throw new Error("Sheets is not configured");
    try { return (await readRanges(ENGINE_SHEET, [`'${AGENT_CASES_TAB}'!A1:F20000`]))?.[0] || []; }
    catch (e) { if (String(e).includes("Unable to parse range")) return []; throw e; } // the tab is not created yet
  },
  async append(cells) { await appendRow(AGENT_CASES_TAB, cells); },
};
export class SheetsCaseStore implements CaseStore {
  constructor(private io: CaseIo = sheetsIo) {}
  async save(c: AgentCase) { await this.io.append(caseToCells(c)); }
  async get(workspace: string, id: string) { return (await this.list(workspace, Infinity)).find((c) => c.id === id) || null; }
  async list(workspace: string, n = 50) {
    if (!workspace || asWs(workspace) !== workspace) return []; // an unreadable workspace never falls back to the default one
    return latest((await this.io.read()).map(cellsToCase).filter((c): c is AgentCase => !!c && c.workspace === workspace)).slice(0, n);
  }
}
