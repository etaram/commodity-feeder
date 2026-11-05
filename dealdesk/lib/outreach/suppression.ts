import { asWs } from "@/lib/auth";
import { latest, nextRev, sha, type Snapshot, type Store } from "./store";

// Suppression list, per workspace. An entry is an exact address ("name@acme.com") or a whole domain ("@acme.com").
// campaign_id "*" applies to every campaign in the workspace (opt-outs and hard bounces are always "*").
// Rows: id = hash of ws|campaign|value, status active|removed (latest wins). Removal is an admin action.
export type SuppressionEntry = { value: string; campaign_id: string; reason: string; source: string; status: "active" | "removed"; at: string; by: string };

export function normSuppression(v: string): string | null {
  const x = String(v || "").trim().toLowerCase().replace(/^mailto:/, "");
  if (/^[^\s@<>"',;]+@[^\s@<>"',;]+\.[a-z]{2,}$/.test(x)) return x;
  const d = x.replace(/^@/, "");
  if (/^([a-z0-9-]+\.)+[a-z]{2,}$/.test(d)) return "@" + d;
  return null;
}

export function suppressionEntries(snap: Snapshot, ws: string): SuppressionEntry[] {
  return [...latest(snap.suppression, ws).values()].map((r) => r.data as unknown as SuppressionEntry);
}

export function isSuppressed(snap: Snapshot, ws: string, email: string, campaignId: string): SuppressionEntry | null {
  const e = String(email || "").trim().toLowerCase();
  if (!e) return null;
  const dom = "@" + e.split("@")[1];
  for (const s of suppressionEntries(snap, ws)) {
    if (s.status !== "active") continue;
    if (s.campaign_id !== "*" && s.campaign_id !== campaignId) continue;
    if (s.value === e || s.value === dom) return s;
  }
  return null;
}

export async function addSuppression(ctx: { store: Store; now: () => number }, ws: string, value: string, reason: string, source: string, by: string, campaignId = "*", status: "active" | "removed" = "active"): Promise<SuppressionEntry> {
  ws = asWs(ws);
  const v = normSuppression(value);
  if (!v) throw new Error("not an email address or domain");
  const cid = campaignId || "*";
  const at = new Date(ctx.now()).toISOString();
  const entry: SuppressionEntry = { value: v, campaign_id: cid, reason: String(reason || "").slice(0, 200), source: String(source || "").slice(0, 200), status, at, by };
  await ctx.store.append("suppression", { time: at, ws, campaign_id: cid, id: `SUP-${sha(`${ws}|${cid}|${v}`).slice(0, 16)}`, rev: nextRev(ctx.now()), status, data: entry, by });
  return entry;
}
