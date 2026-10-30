import { appendRow, sheetsEnabled } from "@/lib/sheets";

// Server-side event log kept in a hidden tab ("App Log") of the Leads Engine sheet, for later fixes and fault tracking.
// Columns: time (Israel), level, area, message, detail, who, env, deployment. Never log secrets or request bodies.
// Failures to log never break a request. The same message is written at most once per 10 minutes per instance.
const seen = new Map<string, number>();
let writes = 0, day = "";

const clean = (v: unknown, n: number) => String(v ?? "").replace(/(sk-[A-Za-z0-9_-]{8,}|Bearer\s+[A-Za-z0-9._-]{12,})/g, "[redacted]").slice(0, n);

export async function logEvent(level: "error" | "warn" | "info", area: string, message: unknown, detail?: unknown, who = "") {
  try {
    const msg = clean(message, 300);
    console[level === "info" ? "log" : level](`[${area}] ${msg}`);
    if (!sheetsEnabled()) return;
    const d = new Date().toISOString().slice(0, 10);
    if (d !== day) { day = d; writes = 0; seen.clear(); }
    const key = `${area}|${msg}`;
    if (writes >= 400 || Date.now() - (seen.get(key) || 0) < 600_000) return;
    seen.set(key, Date.now()); writes++;
    const t = new Date().toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 19);
    await appendRow("App Log", [t, level, area, msg, clean(detail, 800), clean(who, 80), process.env.VERCEL_ENV || "local", (process.env.VERCEL_DEPLOYMENT_ID || "").slice(-8)]);
  } catch { /* logging must never fail a request */ }
}
