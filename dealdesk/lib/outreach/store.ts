import { createHash } from "crypto";
import { asWs } from "@/lib/auth";

// Storage for the outreach engine: append-only rows, latest revision per (ws, id) wins. One tab per entity.
// Every row: A time, B ws, C campaign_id, D id, E rev, F status, G data (JSON), H by.
// The engine only talks to the Store interface, so tests run against MemoryStore and production against SheetsStore
// (lib/outreach/store-sheets.ts). Sheets has no transactions: run one tick at a time (one cron, no parallel ticks).
export const TABS = {
  campaigns: "Campaigns",
  accounts: "Campaign Accounts",
  outbox: "Outbox",
  suppression: "Suppression",
  log: "Outreach Log",
  linkedin: "LinkedIn Tasks",
} as const;
export type TabKey = keyof typeof TABS;
export const TAB_KEYS = Object.keys(TABS) as TabKey[];

export type Row = { time: string; ws: string; campaign_id: string; id: string; rev: string; status: string; data: Record<string, unknown>; by: string };
export type Snapshot = Record<TabKey, Row[]>;

export interface Store {
  load(): Promise<Snapshot>;
  append(tab: TabKey, row: Row): Promise<void>;
}

export const emptySnapshot = (): Snapshot => ({ campaigns: [], accounts: [], outbox: [], suppression: [], log: [], linkedin: [] });

// Monotonic revision string: zero-padded ms clock plus a per-process sequence, compared as text.
let seq = 0;
export function nextRev(nowMs: number): string {
  seq = (seq + 1) % 1_000_000;
  return `${String(Math.floor(nowMs)).padStart(14, "0")}-${String(seq).padStart(6, "0")}`;
}

export const sha = (v: string) => createHash("sha256").update(v).digest("hex");

// Stable JSON (sorted keys) so the same scope always hashes the same.
export function canonical(v: unknown): string {
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  if (v && typeof v === "object") {
    const o = v as Record<string, unknown>;
    return "{" + Object.keys(o).sort().filter((k) => o[k] !== undefined).map((k) => JSON.stringify(k) + ":" + canonical(o[k])).join(",") + "}";
  }
  return JSON.stringify(v ?? null);
}

export const rowWs = (r: Row) => asWs(r.ws);

// Rows of one workspace only. Every read in the engine goes through this (cross-workspace isolation).
export const inWs = (rows: Row[], ws: string) => rows.filter((r) => rowWs(r) === asWs(ws));

// Latest revision per id within one workspace.
export function latest(rows: Row[], ws: string): Map<string, Row> {
  const m = new Map<string, Row>();
  for (const r of inWs(rows, ws)) {
    const cur = m.get(r.id);
    if (!cur || r.rev > cur.rev) m.set(r.id, r);
  }
  return m;
}

export class MemoryStore implements Store {
  snap: Snapshot = emptySnapshot();
  async load(): Promise<Snapshot> {
    const out = emptySnapshot();
    for (const k of TAB_KEYS) out[k] = this.snap[k].map((r) => ({ ...r, data: JSON.parse(JSON.stringify(r.data)) }));
    return out;
  }
  async append(tab: TabKey, row: Row): Promise<void> {
    this.snap[tab].push({ ...row, data: JSON.parse(JSON.stringify(row.data)) });
  }
}

export const MAX_JSON = 45_000;
export function rowToCells(r: Row): string[] {
  const json = JSON.stringify(r.data);
  if (json.length > MAX_JSON) throw new Error(`row ${r.id} is too large to store (${json.length} chars)`);
  return [r.time, asWs(r.ws), r.campaign_id, r.id, r.rev, r.status, json, r.by.slice(0, 120)];
}
export function cellsToRow(c: string[]): Row | null {
  if (!c || !c[3] || !c[4]) return null;
  let data: Record<string, unknown> = {};
  try { data = JSON.parse(c[6] || "{}"); } catch { return null; }
  return { time: c[0] || "", ws: c[1] || "", campaign_id: c[2] || "", id: c[3], rev: c[4], status: c[5] || "", data, by: c[7] || "" };
}
