import { appendRow, ENGINE_SHEET, readRanges, sheetsEnabled } from "./sheets";
import type { Session } from "./auth";

// Who did what in the system, for the admin: one row per action in the hidden 'Activity' tab of the engine sheet.
// Columns: A time (Israel), B email, C name, D role, E action, F target, G detail.
// Never stores passwords, tokens or full AI prompts. Logging never fails the request it describes.
export type ActivityRow = { time: string; email: string; name: string; role: string; action: string; target: string; detail: string };
const TAB = "Activity";
const now = () => new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 19);
const cut = (v: unknown, n: number) => String(v ?? "").replace(/[\r\n\t]+/g, " ").slice(0, n);

export async function logActivity(who: Pick<Session, "email"> & Partial<Session>, action: string, target = "", detail = "") {
  if (!sheetsEnabled()) return;
  try {
    await appendRow(TAB, [now(), cut(who.email, 120), cut(who.name, 80), cut(who.role, 12), cut(action, 40), cut(target, 300), cut(detail, 500)]);
  } catch { /* never block the user's action */ }
}

export async function readActivity(email = "", limit = 500): Promise<ActivityRow[]> {
  const rows = (await readRanges(ENGINE_SHEET, [`'${TAB}'!A2:G50000`]).catch(() => null))?.[0] || [];
  const e = email.trim().toLowerCase();
  const out: ActivityRow[] = [];
  for (let i = rows.length - 1; i >= 0 && out.length < limit; i--) {
    const r = rows[i];
    if (!r || !r[0]) continue;
    if (e && String(r[1] || "").toLowerCase() !== e) continue;
    out.push({ time: r[0] || "", email: r[1] || "", name: r[2] || "", role: r[3] || "", action: r[4] || "", target: r[5] || "", detail: r[6] || "" });
  }
  return out;
}
