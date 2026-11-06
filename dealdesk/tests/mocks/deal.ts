export const SAVED: unknown[] = [];
export function clean(_k: string, d: Record<string, unknown>) { return d.name === "" ? { ok: false, error: "name is required" } : { ok: true, data: d, status: "candidate" }; }
export async function readDeal() { return { records: [], versions: 0 }; }
export async function saveRecord(...a: unknown[]) { SAVED.push(a); }
export type Kind = string;
