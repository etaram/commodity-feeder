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
  return new JWT({
    email: key.client_email,
    key: key.private_key,
    scopes: ["https://www.googleapis.com/auth/spreadsheets"],
  });
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

async function append(tab: string, row: (string | number)[]) {
  const jwt = await client();
  if (!jwt) throw new Error("Sheets is not configured (GOOGLE_SERVICE_ACCOUNT_JSON is missing)");
  const range = encodeURIComponent(`'${tab}'!A1`);
  try {
    await call(jwt, "POST", `${API}/${SHEET}/values/${range}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS`, { values: [row] });
  } catch (e: unknown) {
    if (String(e).includes("Unable to parse range")) {
      await call(jwt, "POST", `${API}/${SHEET}:batchUpdate`, { requests: [{ addSheet: { properties: { title: tab, hidden: true } } }] });
      await call(jwt, "POST", `${API}/${SHEET}/values/${range}:append?valueInputOption=USER_ENTERED&insertDataOption=INSERT_ROWS`, { values: [row] });
    } else throw e;
  }
}

const now = () => new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 16);

/** One row per human decision; the qualification analyst reads this tab. */
export async function recordDecision(id: string, decision: string, email: string, note: string, title: string, buyer: string, country: string) {
  await append("Decisions", [id, decision, email, now(), note, title.slice(0, 200), buyer.slice(0, 120), country]);
}

/** Queues a job for the Panel worker agent (same format the in-sheet panel uses). */
export async function queueJob(type: string, targetId: string, target: string, context: string, request: string, email: string) {
  const jobId = `WEB-${Date.now().toString(36).toUpperCase()}`;
  await append("Panel Jobs", [jobId, now(), type, targetId, target.slice(0, 200), context.slice(0, 1500), request.slice(0, 1000), "queued", "", "", now(), `from ${email}`]);
  return jobId;
}
