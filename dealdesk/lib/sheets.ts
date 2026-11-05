import { JWT } from "google-auth-library";

const SHEET = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y";
const API = "https://sheets.googleapis.com/v4/spreadsheets";

export function sheetsEnabled(): boolean {
  return Boolean(process.env.GOOGLE_SERVICE_ACCOUNT_JSON);
}

// One client per instance: the JWT caches its access token (about an hour), so reads no longer ask Google for a new
// token every call (ten parallel page reads used to queue ten token requests and time out together).
let jwtClient: JWT | null = null;
async function client(): Promise<JWT | null> {
  const raw = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!raw) return null;
  if (jwtClient) return jwtClient;
  const key = JSON.parse(raw);
  jwtClient = new JWT({ email: key.client_email, key: key.private_key, scopes: ["https://www.googleapis.com/auth/spreadsheets"] });
  return jwtClient;
}

// Every Sheets request has a hard time limit: a stalled Google API must never hold a request until the 60 s function
// limit (on 5 November a stall made every panel read time out together). Callers already fall back to a copy.
const SHEETS_TIMEOUT_MS = Number(process.env.SHEETS_TIMEOUT_MS || 12000);
async function call(jwt: JWT, method: string, url: string, body?: unknown) {
  const { token } = await jwt.getAccessToken();
  const r = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(SHEETS_TIMEOUT_MS),
  });
  if (!r.ok) throw new Error(`Sheets ${r.status}: ${(await r.text()).slice(0, 300)}`);
  return r.json();
}

// Reads several ranges at once (any spreadsheet the service account can open). Returns null when not configured.
export async function readRanges(sid: string, ranges: string[]): Promise<string[][][] | null> {
  const jwt = await client();
  if (!jwt) return null;
  const q = ranges.map((r) => "ranges=" + encodeURIComponent(r)).join("&");
  const j = await call(jwt, "GET", `${API}/${sid}/values:batchGet?${q}&valueRenderOption=FORMATTED_VALUE`);
  return (j.valueRanges || []).map((v: { values?: string[][] }) => v.values || []);
}

// One supplier's official contact details from the private Supplier Universe sheet (columns B name, C country,
// AA email, AB phone, AC website, AD website source, AE address, AF company ID), looked up with a server-side query.
export const UNIVERSE = "1crzrRr4qrgt1WpAwNmCNPL4TfIrZUuTyqRGonVvwhuA";
export async function lookupContact(name: string, country: string): Promise<Record<string, string> | null> {
  const jwt = await client();
  if (!jwt || !name) return null;
  if (name.length > 200 || country.length > 80) return null;
  const clean = (v: string) => v.replace(/[\\\r\n\t]/g, " ");
  const lit = (v: string) => (clean(v).includes("'") ? `"${clean(v).replace(/"/g, "")}"` : `'${clean(v)}'`);
  const tq = `select B,C,AA,AB,AC,AD,AE,AF where B = ${lit(name)}${country ? ` and C = ${lit(country)}` : ""} limit 1`;
  const { token } = await jwt.getAccessToken();
  const url = `https://docs.google.com/spreadsheets/d/${UNIVERSE}/gviz/tq?sheet=Suppliers&tqx=out:json&tq=${encodeURIComponent(tq)}`;
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(SHEETS_TIMEOUT_MS) });
  if (!r.ok) throw new Error(`lookup ${r.status}`);
  const txt = await r.text();
  const j = JSON.parse(txt.slice(txt.indexOf("{"), txt.lastIndexOf("}") + 1));
  const row = j?.table?.rows?.[0]?.c;
  if (!row) return null;
  const v = (i: number) => String(row[i]?.v ?? "").trim();
  return { email: v(2), phone: v(3), website: v(4), website_source: v(5), address: v(6), legal_id: v(7) };
}

export async function appendRow(tab: string, row: (string | number)[]) {
  return append(tab, row);
}

// Several rows in one request (one API call instead of one per row); creates the hidden tab on first use.
export async function appendRows(tab: string, rows: (string | number)[][]) {
  if (!rows.length) return;
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  const range = encodeURIComponent(`'${tab}'!A1`);
  const url = `${API}/${SHEET}/values/${range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  const values = rows.map((r) => r.slice(0, 40));
  try {
    await call(jwt, "POST", url, { values });
  } catch (e: unknown) {
    if (String(e).includes("Unable to parse range")) {
      await call(jwt, "POST", `${API}/${SHEET}:batchUpdate`, { requests: [{ addSheet: { properties: { title: tab, hidden: true } } }] });
      await call(jwt, "POST", url, { values });
    } else throw e;
  }
}

// Overwrites one range of the engine sheet (RAW, never evaluated as formulas). Used for the Users tab only.
export async function writeRange(range: string, values: (string | number)[][]) {
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  await call(jwt, "PUT", `${API}/${SHEET}/values/${encodeURIComponent(range)}?valueInputOption=RAW`, { range, values });
}

export const ENGINE_SHEET = SHEET;

// A server-side query on one tab of a spreadsheet (Google Visualization query language): returns the matching rows
// only, so a lookup in a 30,000-row tab does not download the tab. The caller builds the query from fixed column
// letters; values go through q() below.
export const gvizLit = (v: string) => { const c = String(v).replace(/[\\\r\n\t]/g, " "); return c.includes("'") ? `"${c.replace(/"/g, "")}"` : `'${c}'`; };
export async function gviz(sid: string, sheet: string, tq: string): Promise<string[][]> {
  const jwt = await client();
  if (!jwt) return [];
  const { token } = await jwt.getAccessToken();
  const url = `https://docs.google.com/spreadsheets/d/${sid}/gviz/tq?sheet=${encodeURIComponent(sheet)}&tqx=out:json&tq=${encodeURIComponent(tq)}`;
  const r = await fetch(url, { headers: { Authorization: `Bearer ${token}` }, signal: AbortSignal.timeout(SHEETS_TIMEOUT_MS) });
  if (!r.ok) throw new Error(`gviz ${r.status}`);
  const txt = await r.text();
  const j = JSON.parse(txt.slice(txt.indexOf("{"), txt.lastIndexOf("}") + 1));
  if (j.status === "error") throw new Error(`gviz: ${String(j.errors?.[0]?.detailed_message || j.errors?.[0]?.message || "error").slice(0, 160)}`);
  return (j?.table?.rows || []).map((row: { c: ({ v?: unknown; f?: string } | null)[] }) => (row.c || []).map((c) => String(c?.f ?? c?.v ?? "")));
}

// RAW: a cell typed by a user is stored as text and never evaluated as a formula (=, +, -, @ at the start are harmless).
// Appends one row to a tab of another spreadsheet the service account can edit (the private Supplier Universe).
export async function appendTo(sid: string, tab: string, row: (string | number)[]) {
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  const range = encodeURIComponent(`'${tab}'!A1`);
  await call(jwt, "POST", `${API}/${sid}/values/${range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`, { values: [row.slice(0, 40)] });
}

async function append(tab: string, row: (string | number)[]) {
  if (row.length > 40) row = row.slice(0, 40);
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  const range = encodeURIComponent(`'${tab}'!A1`);
  const url = `${API}/${SHEET}/values/${range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  try {
    await call(jwt, "POST", url, { values: [row] });
  } catch (e: unknown) {
    if (String(e).includes("Unable to parse range")) {
      await call(jwt, "POST", `${API}/${SHEET}:batchUpdate`, { requests: [{ addSheet: { properties: { title: tab, hidden: true } } }] });
      await call(jwt, "POST", url, { values: [row] });
    } else throw e;
  }
}

const now = () => new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 16);

export async function recordDecision(id: string, decision: string, email: string, note: string, title: string, buyer: string, country: string) {
  await append("Decisions", [id, decision, email, now(), note, title.slice(0, 200), buyer.slice(0, 120), country]);
}

export async function queueJob(type: string, targetId: string, target: string, context: string, request: string, email: string) {
  const jobId = `WEB-${Date.now().toString(36).toUpperCase()}`;
  await append("Panel Jobs", [jobId, now(), type, targetId, target.slice(0, 200), context.slice(0, 1500), request.slice(0, 1000), "queued", "", "", now(), `from ${email}`]);
  return jobId;
}

// Research runs already logged today (UTC) in the 'Panel Jobs' tab: a limit shared by every server instance, unlike a counter in memory.
let jt: { at: number; n: number } | null = null;
export async function jobsToday(): Promise<number> {
  if (jt && Date.now() - jt.at < 20_000) return jt.n;
  const v = (await readRanges(SHEET, ["'Panel Jobs'!B2:B5000"]))?.[0] || [];
  const d = new Date().toISOString().slice(0, 10);
  const n = v.filter((r) => String(r[0] || "").startsWith(d)).length;
  jt = { at: Date.now(), n };
  return n;
}
