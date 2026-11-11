import { JWT } from "google-auth-library";

const SHEET = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y";
const API = "https://sheets.googleapis.com/v4/spreadsheets";

// The tabs the app itself writes all the time (logs, bot memory, agent state) live in a small separate spreadsheet
// when STATE_SHEET_ID is set. A write to the engine sheet (4.7 million cells) holds its reads for up to a minute, so
// every log line used to stall the live panel tabs; the state sheet takes those writes instead. Unset = old behaviour.
const STATE_TABS = new Set(["Activity", "App Log", "AI Usage", "Telegram Chat", "Telegram", "Agent Runs", "Agent Approvals", "Locks", "Tender Projects", "Tender Watches", "Coverage Cache", "Briefs",
  // read on every request or written by the app only: users and their settings, push subscriptions, app records
  "Users", "Profiles", "Push", "Workspace strategy", "Client Dossiers", "Prospects", "My Network", "Assertions", "Decisions", "Outbox",
  // missions (lib/missionstore-sheets.ts): append-only rows, created hidden on the first append
  "Missions",
  // outcome ledger (lib/outcomestore-sheets.ts): append-only rows, created hidden on the first append
  "Outcomes",
  // idempotency keys of real e-mail sends (lib/sendguard.ts): written and read back around every send, so it must be fast
  "Send Guard",
  // decisions of the scouts (lib/scout.ts): append-only rows, created hidden on the first append
  "Scout Seen"]);
const tabOf = (range: string) => (range.match(/^'([^']+)'/) || range.match(/^([^!]+)!/) || [])[1] || range;
// A test copy of the site (staging) must never write to the live spreadsheets. Two settings make that a property of the
// code, not of care: STATE_TABS_EXTRA names further tabs that live in the state sheet (in staging: every tab the app
// writes that is still in the engine sheet, e.g. the outreach lists), and SHEETS_READONLY_IDS lists spreadsheets that
// refuse every write (in staging: the engine sheet, the live state sheet and the supplier universe).
const extraTabs = () => new Set((process.env.STATE_TABS_EXTRA || "").split(",").map((x) => x.trim()).filter(Boolean));
export function sheetFor(tab: string): string {
  const st = (process.env.STATE_SHEET_ID || "").trim();
  return st && (STATE_TABS.has(tab) || extraTabs().has(tab)) ? st : SHEET;
}
/** The spreadsheet a write would hit, when that spreadsheet is marked read-only; "" when the write is allowed. */
export function writeRefused(method: string, url: string): string {
  if (method === "GET") return "";
  const id = (url.match(/\/spreadsheets\/([^/:?]+)/) || [])[1] || "";
  return (process.env.SHEETS_READONLY_IDS || "").split(",").map((x) => x.trim()).filter(Boolean).includes(id) ? id : "";
}
export function stateSheet(): string { return sheetFor("Activity"); }

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
  const ro = writeRefused(method, url);
  if (ro) throw new Error(`Sheets write refused: spreadsheet ${ro.slice(0, 6)}... is read-only in this environment`);
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

// Timing of one read in parts (token, request), for the self-check
export async function sheetsDiag(): Promise<Record<string, number | string>> {
  const out: Record<string, number | string> = {};
  let t = Date.now();
  const jwt = await client(); if (!jwt) return { error: "no service account" };
  try { await jwt.getAccessToken(); out.token_ms = Date.now() - t; } catch (e) { out.token_err = String(e).slice(0, 160); }
  t = Date.now();
  try { await call(jwt, "GET", `${API}/${SHEET}/values:batchGet?ranges=${encodeURIComponent("'Users'!A1:B3")}`); out.read_ms = Date.now() - t; } catch (e) { out.read_err = String(e).slice(0, 160); out.read_ms = Date.now() - t; }
  t = Date.now();
  try { await call(jwt, "GET", `${API}/${SHEET}/values:batchGet?ranges=${encodeURIComponent("'Users'!A1:B3")}`); out.read2_ms = Date.now() - t; } catch (e) { out.read2_err = String(e).slice(0, 160); }
  const { token } = await jwt.getAccessToken();
  const probe = async (name: string, url: string, auth = true) => {
    const t0 = Date.now();
    try { const r = await fetch(url, { headers: auth ? { Authorization: `Bearer ${token}` } : {}, signal: AbortSignal.timeout(12000) }); out[name] = `${r.status} ${Date.now() - t0}ms ${(await r.text()).length}b`; }
    catch (e) { out[name] = `ERR ${Date.now() - t0}ms ${String(e).slice(0, 60)}`; }
  };
  await probe("noauth_values", `${API}/${SHEET}/values/${encodeURIComponent("'Users'!A1:B3")}`, false);
  await probe("meta_title", `${API}/${SHEET}?fields=properties.title`);
  await probe("values_get", `${API}/${SHEET}/values/${encodeURIComponent("'Users'!A1:B3")}`);
  await probe("su_values", `${API}/1crzrRr4qrgt1WpAwNmCNPL4TfIrZUuTyqRGonVvwhuA/values/${encodeURIComponent("'Stats'!A1:B3")}`);
  await probe("sa_email_domain", "https://www.googleapis.com/discovery/v1/apis?name=drive", false);
  out.sa = String(JSON.parse(process.env.GOOGLE_SERVICE_ACCOUNT_JSON || "{}").client_email || "").replace(/^[^@]{0,3}[^@]*@/, (m) => m.slice(0, 3) + "...@");
  t = Date.now();
  try { await fetch("https://www.googleapis.com/discovery/v1/apis?name=sheets", { signal: AbortSignal.timeout(15000) }); out.plain_fetch_ms = Date.now() - t; } catch (e) { out.plain_err = String(e).slice(0, 120); }
  return out;
}

// Reads several ranges at once (any spreadsheet the service account can open). Returns null when not configured.
export async function readRanges(sid: string, ranges: string[]): Promise<string[][][] | null> {
  const jwt = await client();
  if (!jwt) return null;
  // engine-sheet ranges of the state tabs are read from the state sheet (see STATE_TABS), in the order asked
  const where = ranges.map((r) => (sid === SHEET ? sheetFor(tabOf(r)) : sid));
  const out: string[][][] = new Array(ranges.length);
  for (const id of [...new Set(where)]) {
    const idx = ranges.map((_, i) => i).filter((i) => where[i] === id);
    const q = idx.map((i) => "ranges=" + encodeURIComponent(ranges[i])).join("&");
    const j = await call(jwt, "GET", `${API}/${id}/values:batchGet?${q}&valueRenderOption=FORMATTED_VALUE`);
    (j.valueRanges || []).forEach((v: { values?: string[][] }, k: number) => { out[idx[k]] = v.values || []; });
  }
  return out.map((v) => v || []);
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
  const range = encodeURIComponent(`'${tab}'!A1`), sid = sheetFor(tab);
  const url = `${API}/${sid}/values/${range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  const values = rows.map((r) => r.slice(0, 40));
  try {
    await call(jwt, "POST", url, { values });
  } catch (e: unknown) {
    if (String(e).includes("Unable to parse range")) {
      await call(jwt, "POST", `${API}/${sid}:batchUpdate`, { requests: [{ addSheet: { properties: { title: tab, hidden: true } } }] });
      // a new tab starts with a marker row: every reader starts at row 2, and without it the first record was never read
      await call(jwt, "POST", url, { values: [["#"], ...values] });
    } else throw e;
  }
}

// Overwrites one range of the engine sheet (RAW, never evaluated as formulas). Used for the Users tab only.
export async function writeRange(range: string, values: (string | number)[][]) {
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  await call(jwt, "PUT", `${API}/${sheetFor(tabOf(range))}/values/${encodeURIComponent(range)}?valueInputOption=RAW`, { range, values });
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
// Many rows to a tab of any spreadsheet in one request; creates the tab (with the given header) when it is missing.
export async function appendManyTo(sid: string, tab: string, rows: (string | number)[][], header?: string[]) {
  if (!rows.length) return;
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  const url = `${API}/${sid}/values/${encodeURIComponent(`'${tab}'!A1`)}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  try {
    await call(jwt, "POST", url, { values: rows.map((r) => r.slice(0, 40)) });
  } catch (e: unknown) {
    if (!String(e).includes("Unable to parse range")) throw e;
    await call(jwt, "POST", `${API}/${sid}:batchUpdate`, { requests: [{ addSheet: { properties: { title: tab } } }] });
    await call(jwt, "POST", url, { values: [...(header ? [header] : []), ...rows.map((r) => r.slice(0, 40))] });
  }
}

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
  const range = encodeURIComponent(`'${tab}'!A1`), sid = sheetFor(tab);
  const url = `${API}/${sid}/values/${range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS`;
  try {
    await call(jwt, "POST", url, { values: [row] });
  } catch (e: unknown) {
    if (String(e).includes("Unable to parse range")) {
      await call(jwt, "POST", `${API}/${sid}:batchUpdate`, { requests: [{ addSheet: { properties: { title: tab, hidden: true } } }] });
      await call(jwt, "POST", url, { values: [["#"], row] });   // marker row first: readers start at row 2
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
