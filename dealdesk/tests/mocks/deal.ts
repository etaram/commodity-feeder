export const SAVED: unknown[] = [];
export function clean(_k: string, d: Record<string, unknown>) { return d.name === "" ? { ok: false, error: "name is required" } : { ok: true, data: d, status: "candidate" }; }
// what was saved is read back (args of saveRecord: deal, kind, record id, version, status, data, by, note, workspace)
export async function readDeal(dealId?: string) {
  const records = (SAVED as unknown[][]).filter((a) => a[0] === dealId).map((a) => ({ kind: String(a[1]), record_id: String(a[2]), version: Number(a[3]), status: String(a[4]), data: a[5] as Record<string, unknown>, by: String(a[6]), source: "panel", note: String(a[7] || "") }));
  return { records, versions: records.length };
}
export async function saveRecord(...a: unknown[]) { SAVED.push(a); }
export type Kind = string;
