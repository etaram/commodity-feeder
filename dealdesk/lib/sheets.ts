import { JWT } from "google-auth-library";

const SHEET = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y";
const API = "https://sheets.googleapis.com/v4/spreadsheets";

export function sheetsEnabled(): boolean {
  return Boolean(process.env.GOOGLE_SERVICE_ACCOUNT_JSON);
}

async function client(): Promise<JWT | null> {
  const raw = process.env.GOOGLE_SERVICE_ACCOUNT_JSON;
  if (!raw) return null;
  const key = JSON.parse(raw);
  return new JWT({ email: key.client_email, key: key.private_key, scopes: ["https://www.googleapis.com/auth/spreadsheets"] });
}

async function call(jwt: JWT, method: string, url: string, body?: unknown) {
  const { token } = await jwt.getAccessToken();
  const r = await fetch(url, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
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

export async function appendRow(tab: string, row: (string | number)[]) {
  return append(tab, row);
}

async function append(tab: string, row: (string | number)[]) {
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured");
  const range = encodeURIComponent(`'${tab}'!A1`);
  const url = `${API}/${SHEET}/values/${range}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS`;
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
