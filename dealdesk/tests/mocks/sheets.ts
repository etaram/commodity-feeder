export const ENGINE_SHEET = "E";
export const TABS: Record<string, (string | number)[][]> = {};
export async function appendRow(tab: string, row: (string | number)[]) { (TABS[tab] ||= []).push(row.map((x) => x)); }
export async function readRanges(_s: string, ranges: string[]) { const tab = ranges[0].match(/'([^']+)'/)![1]; return [(TABS[tab] || []).map((r) => r.map(String))]; }
export async function lookupContact(name: string) { return name === "Grain SA" ? { email: "sales@grainsa.co.za", phone: "+27115550000", website: "https://grainsa.co.za" } : null; }
export const sheetsEnabled = () => true;
