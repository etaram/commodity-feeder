import { appendRow, appendRows, readRanges, ENGINE_SHEET, UNIVERSE } from "@/lib/sheets";
import { COLUMNS, assertionsFromVerifiedCaps, fromGrid, toRow, type Assertion } from "@/lib/assertions";

// Storage for the assertions ledger: hidden tab 'Assertions' in the engine sheet, append-only, one row per version,
// columns in COLUMNS order. appendRow creates the tab on first write; the header is written once with it.
export const TAB = "Assertions";
const TTL = 300_000; // 5 minutes

let cache: { at: number; rows: Assertion[]; header: boolean } | null = null;
let flight: Promise<Assertion[]> | null = null;

export async function readAssertions(fresh = false): Promise<Assertion[]> {
  if (!fresh && cache && Date.now() - cache.at < TTL) return cache.rows;
  if (!flight) {
    flight = (async () => {
      const grid = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A1:P20000`]).catch(() => null))?.[0] || [];
      const rows = fromGrid(grid);
      cache = { at: Date.now(), rows, header: grid.length > 0 };
      return rows;
    })().finally(() => { flight = null; });
  }
  return flight;
}

// Appends one version. The in-memory cache is extended at once so a read right after a write sees the row on this
// instance; other instances see it within TTL.
export async function appendAssertions(list: Assertion[]): Promise<void> {
  if (!list.length) return;
  if (!cache) await readAssertions();
  const rows = list.map(toRow);
  if (cache && !cache.header) { rows.unshift([...COLUMNS]); cache.header = true; }
  await appendRows(TAB, rows);
  if (cache) cache.rows = [...cache.rows, ...list];
}

export async function appendAssertion(a: Assertion): Promise<void> {
  if (!cache) await readAssertions();
  if (cache && !cache.header) { await appendRow(TAB, [...COLUMNS]); cache.header = true; }
  await appendRow(TAB, toRow(a));
  if (cache) cache.rows = [...cache.rows, a];
}

// One-way import of 'Verified capabilities' (UNIVERSE sheet) into the ledger. Not run automatically: the integrator
// calls it once (for example from a one-off admin route or a script). Idempotent on id, so a second call appends only
// rows that are new since the first. Returns how many rows were appended.
export async function importVerifiedCaps(limit = 5000): Promise<{ imported: number; skipped: number }> {
  const grid = (await readRanges(UNIVERSE, ["'Verified capabilities'!A1:I20000"]).catch(() => null))?.[0] || [];
  const have = new Set((await readAssertions(true)).map((r) => r.id));
  let imported = 0, skipped = 0;
  for (const a of assertionsFromVerifiedCaps(grid)) {
    if (have.has(a.id)) { skipped++; continue; }
    if (imported >= limit) break;
    await appendAssertion(a);
    have.add(a.id);
    imported++;
  }
  return { imported, skipped };
}
