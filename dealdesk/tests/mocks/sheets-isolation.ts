// Sheet stand-in for tests/isolation.test.ts: every export of the real module, with everything that reads or writes
// replaced by in-memory tabs (one grid per tab name, whatever spreadsheet is asked). No credentials, no network.
export * from "../../lib/sheets";
export const TABS: Record<string, (string | number)[][]> = {};
export const WRITES: { tab: string; row: (string | number)[] }[] = [];
const put = (tab: string, row: (string | number)[]) => { (TABS[tab] ||= []).push([...row]); WRITES.push({ tab, row: [...row] }); };
const tabOf = (range: string) => (range.match(/^'([^']+)'/) || range.match(/^([^!]+)!/) || [])[1] || range;
export const sheetsEnabled = () => true;
export async function appendRow(tab: string, row: (string | number)[]) { put(tab, row); }
export async function appendRows(tab: string, rows: (string | number)[][]) { for (const r of rows) put(tab, r); }
export async function appendTo(_sid: string, tab: string, row: (string | number)[]) { put(tab, row); }
export async function appendManyTo(_sid: string, tab: string, rows: (string | number)[][]) { for (const r of rows) put(tab, r); }
export async function readRanges(_sid: string, ranges: string[]) { return ranges.map((x) => (TABS[tabOf(x)] || []).map((r) => r.map(String))); }
export async function writeRange(range: string, values: (string | number)[][]) { const row = Number((range.match(/![A-Z]+(\d+)/) || [])[1] || 0); if (row >= 2) (TABS[tabOf(range)] ||= [])[row - 2] = values[0]; }
export async function gviz() { return [] as string[][]; }
// the original workspace's private Supplier Universe contact columns
export const OWNER_CONTACT = { email: "private-owner-contact@grainsa.example", phone: "+27115550000", website: "https://grainsa.example" };
export async function lookupContact(name: string) { return name === "Grain SA" ? { ...OWNER_CONTACT } : null; }
export async function recordDecision(id: string, decision: string, email: string, note: string, title: string, buyer: string, country: string) { put("Decisions", [id, decision, email, "now", note, title, buyer, country]); }
export async function queueJob(type: string, targetId: string, target: string, context: string, request: string, email: string) { put("Panel Jobs", ["WEB-1", "now", type, targetId, target, context, request, "queued", "", "", "now", `from ${email}`]); return "WEB-1"; }
export async function jobsToday() { return 0; }
