// Reads the rows the operations room is built from (lib/room.ts does the shaping). One read of four tabs plus the
// workspace's missions, kept for 15 seconds per workspace: the screen refreshes every 20 seconds and several open
// screens must not each re-read the run states. A tab that cannot be read is named on the screen, never shown as empty.
import { ENGINE_SHEET, readRanges, sheetsEnabled } from "@/lib/sheets";
import { APPROVALS, RUNS } from "@/lib/dealagent";
import { SEND_GUARD } from "@/lib/sendguard";
import { SCOUT_SEEN } from "@/lib/scout";
import { scoutOn } from "@/lib/scoutrun";
import { sheetsMissionStore } from "@/lib/missionstore-sheets";
import { shapeRoom, type RoomView } from "@/lib/room";
import type { Mission } from "@/lib/mission";

export const roomOn = () => (process.env.OPS_ROOM || "").trim().toLowerCase() === "on";
const cache = new Map<string, { at: number; v: RoomView }>();

export async function loadRoom(ws: string, fresh = false): Promise<RoomView> {
  const hit = cache.get(ws);
  if (!fresh && hit && Date.now() - hit.at < 15_000) return hit.v;
  const errors: string[] = [];
  if (!sheetsEnabled()) errors.push("the state sheet is not configured: nothing can be read");
  // each tab on its own: a tab that does not exist yet (nothing was ever written to it) is an empty list, not a fault
  const tab = async (name: string, range: string): Promise<string[][]> => {
    try { return (await readRanges(ENGINE_SHEET, [`'${name}'!${range}`]))?.[0] || []; }
    catch (e) { if (!String(e).includes("Unable to parse range")) errors.push(`${name}: could not be read`); return []; }
  };
  const [runs, approvals, seen, guard, missions] = await Promise.all([
    tab(RUNS, "A2:G5000"), tab(APPROVALS, "A2:F5000"), tab(SCOUT_SEEN, "A2:K50000"), tab(SEND_GUARD, "A1:D50000"),
    sheetsMissionStore().list(ws).catch((): Mission[] => { errors.push("Missions: could not be read"); return []; })]);
  const v = shapeRoom({ ws, now: Date.now(), runs, approvals, seen, guard, missions, scoutOn: scoutOn(), errors });
  cache.set(ws, { at: Date.now(), v });
  return v;
}
