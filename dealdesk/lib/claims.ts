// A lock for work that must happen once even when two calls arrive together (a double press on Approve, a Telegram
// retry, two chained steps of one agent run). Sheets has no atomic write, so a claim is an appended row: every
// contender appends its own token, reads the rows back, and the earliest live claim for the key wins. Rows are
// appended in order by the Sheets API, so all contenders agree on who was first. A claim expires after its TTL,
// so a crashed holder never blocks the work for good.
import { appendRow, readRanges, ENGINE_SHEET } from "@/lib/sheets";
import crypto from "node:crypto";

export const LOCKS = "Locks";
const held = new Set<string>();  // same instance: no sheet round trip needed to refuse

export async function claim(key: string, ttlMs: number): Promise<{ ok: boolean; release: () => Promise<void> }> {
  const no = { ok: false, release: async () => {} };
  if (held.has(key)) return no;
  const token = crypto.randomUUID(), now = Date.now();
  await appendRow(LOCKS, [key, token, new Date(now).toISOString(), "claim"]);
  const rows = (await readRanges(ENGINE_SHEET, [`'${LOCKS}'!A2:D20000`]).catch(() => null))?.[0] || [];
  const released = new Set(rows.filter((r) => r[0] === key && r[3] === "release").map((r) => r[1]));
  const live = rows.filter((r) => r[0] === key && r[3] === "claim" && !released.has(r[1]) && now - Date.parse(r[2] || "") < ttlMs);
  if (!live.length || live[0][1] !== token) {
    await appendRow(LOCKS, [key, token, new Date().toISOString(), "release"]).catch(() => {});
    return no;
  }
  held.add(key);
  return { ok: true, release: async () => { held.delete(key); await appendRow(LOCKS, [key, token, new Date().toISOString(), "release"]).catch(() => {}); } };
}
