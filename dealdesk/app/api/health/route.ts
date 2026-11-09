import { NextRequest, NextResponse } from "next/server";
import { readRanges, ENGINE_SHEET, sheetsDiag } from "@/lib/sheets";
import { mailCheck } from "@/lib/mailer";
import { claude } from "@/lib/anthropic";
import { tgEnv } from "@/lib/tgenv";
import { botSelfTest } from "@/lib/telegram";

// Self-check: calls every panel route the way the panel does (read-only calls only) and reports status, time, size
// and the first error, plus the Telegram webhook, the AI key, the mail box login and the bot's tabs. Nothing is
// written, sent or changed. Open with the AUDIT_TOKEN (Bearer, or ?t=) while an audit runs; CRON_SECRET also works.
export const dynamic = "force-dynamic";
export const maxDuration = 300;

const KEYS = ["tenders", "titles", "bd", "accounts", "repeat", "markets", "plays", "fx", "attention", "meta", "intel", "upcoming", "stats", "pursuits",
  "jobs", "suppliers", "grants", "exempt", "ilex", "integrity", "contacts", "projects", "ptasks", "approvals", "websup", "tot_t", "tot_s"];
type Check = { name: string; method?: "GET" | "POST"; path: string; body?: unknown };
const CHECKS: Check[] = [
  ...KEYS.map((k) => ({ name: `get:${k}`, method: "POST" as const, path: "/api/panel/get", body: { key: k } })),
  { name: "search tenders", method: "POST", path: "/api/panel/search", body: { kind: "t", values: [["\\bsolar"]] } },
  { name: "search tenders he", method: "POST", path: "/api/panel/search", body: { kind: "t", values: [["\\bדאטה סנטר", "country", ""], ["", "min value", ""], ["", "max value", ""], ["", "", ""], [7, "", ""], [2000, "fit", ""]] } },
  { name: "search tenders en7", method: "POST", path: "/api/panel/search", body: { kind: "t", values: [["\\bsolar", "country", ""], ["", "min value", ""], ["", "max value", ""], ["", "", ""], [7, "", ""], [2000, "fit", ""]] } },
  { name: "search suppliers", method: "POST", path: "/api/panel/search", body: { kind: "s", values: [["\\btransformer"]] } },
  { name: "suppliers-for", method: "POST", path: "/api/panel/suppliers-for", body: { sector: "", text: "power transformer", country: "", region: "", hs: "", n: 10 } },
  { name: "commodities coffee", path: "/api/panel/commodities?product=coffee&limit=60" },
  { name: "commodities all", path: "/api/panel/commodities?limit=50" },
  { name: "intel", path: "/api/panel/intel" },
  { name: "country ETH", path: "/api/panel/country?c=ETH" },
  { name: "country ISR", path: "/api/panel/country?c=ISR" },
  { name: "coverage", path: "/api/panel/coverage" },
  { name: "brief he", path: "/api/panel/brief?lang=he" },
  { name: "brief geo", path: "/api/panel/brief?kind=geo&lang=he" },
  { name: "finance", path: "/api/panel/finance" },
  { name: "logistics", path: "/api/panel/logistics" },
  { name: "strategy", path: "/api/panel/strategy" },
  { name: "profile", path: "/api/profile" },
  { name: "profile facets", path: "/api/profile?facets=1" },
  { name: "match", path: "/api/match?mode=" },
  { name: "deal pipeline", path: "/api/deal?pipeline=1" },
  { name: "company-check summary", path: "/api/panel/company-check?summary=1" },
  { name: "assertions", path: "/api/panel/assertions?entity=test" },
  { name: "admin", path: "/api/panel/admin" },
  { name: "ai-usage", path: "/api/panel/ai-usage?days=7" },
  { name: "clients", path: "/api/clients" },
  { name: "campaigns", path: "/api/outreach/campaign" },
  { name: "outbox", path: "/api/outreach/outbox" },
  { name: "outreach log", path: "/api/outreach/log" },
  { name: "suppression", path: "/api/outreach/suppression" },
  { name: "linkedin", path: "/api/outreach/linkedin" },
  { name: "push", path: "/api/push" },
  { name: "telegram code", path: "/api/telegram/code" },
  { name: "telegram setup", path: "/api/telegram/setup" },
  { name: "know", method: "POST", path: "/api/panel/know", body: { names: ["Siemens Energy"] } },
  { name: "users", path: "/api/users" },
  { name: "today", path: "/api/panel/today" },
  { name: "page /", path: "/" },
  { name: "page /panel-shim.js", path: "/panel-shim.js" },
  { name: "page /login", path: "/login" },
];

function summarize(j: unknown): string {
  if (!j || typeof j !== "object") return "";
  const o = j as Record<string, unknown>;
  const parts: string[] = [];
  for (const [k, v] of Object.entries(o)) {
    if (Array.isArray(v)) parts.push(`${k}[${v.length}]`);
    else if (v && typeof v === "object") parts.push(`${k}{${Object.keys(v).length}}`);
    else if (["ok", "error", "code", "total", "count", "at"].includes(k)) parts.push(`${k}=${String(v).slice(0, 80)}`);
  }
  return parts.join(" ").slice(0, 240);
}

export async function GET(req: NextRequest) {
  const tok = process.env.AUDIT_TOKEN || "";
  const given = (req.headers.get("authorization") || "").replace(/^Bearer\s+/i, "") || req.nextUrl.searchParams.get("t") || "";
  const okAuth = (tok.length >= 32 && given === tok) || (process.env.CRON_SECRET && given === process.env.CRON_SECRET);
  if (!okAuth) return NextResponse.json({ ok: false }, { status: 401 });
  if (req.nextUrl.searchParams.get("only") === "bot") return NextResponse.json({ ok: true, bot: await botSelfTest() });
  if (req.nextUrl.searchParams.get("diag")) return NextResponse.json({ ok: true, region: process.env.VERCEL_REGION || "", sheets: await sheetsDiag(), again: await sheetsDiag() });
  const base = `https://${req.headers.get("host")}`;
  const only = req.nextUrl.searchParams.get("only") || "";
  const sample = Number(req.nextUrl.searchParams.get("sample") || 0);
  const out: Record<string, unknown>[] = [];
  const list = only === "extra" ? [] : CHECKS.filter((c) => !only || only.split(",").some((o) => c.name === o || c.name.startsWith(o)));
  // a few at a time, like a page load
  for (let i = 0; i < list.length; i += 6) {
    out.push(...(await Promise.all(list.slice(i, i + 6).map(async (c) => {
      const t0 = Date.now();
      try {
        const r = await fetch(base + c.path, { method: c.method || "GET", headers: { "content-type": "application/json", "x-dd-audit": tok }, body: c.body ? JSON.stringify(c.body) : undefined, signal: AbortSignal.timeout(70000) });
        const txt = await r.text();
        let j: unknown = null; try { j = JSON.parse(txt); } catch { /* html or text */ }
        const values = (j as { values?: unknown[][] })?.values;
        const rows = Array.isArray(values) ? values.length : undefined;
        const head = Array.isArray(values) && Array.isArray(values[0]) ? (values[0] as string[]).slice(0, 40).join("|") : undefined;
        return { name: c.name, status: r.status, ms: Date.now() - t0, rows, head, sum: j ? summarize(j) : `${txt.length} bytes`, err: (j as { error?: string })?.error,
          sample: sample && Array.isArray(values) ? values.slice(0, sample + 1) : undefined };
      } catch (e) { return { name: c.name, status: 0, ms: Date.now() - t0, err: String(e).slice(0, 200) }; }
    }))));
  }
  const extra: Record<string, unknown> = {};
  if (!only || only === "extra") {
    const tg = tgEnv().token;
    extra.telegram_token = Boolean(tg);
    extra.telegram = tg ? await fetch(`https://api.telegram.org/bot${tg}/getWebhookInfo`).then((r) => r.json()).then((j) => { const w = j.result || {}; return { url_set: !!w.url, url_host: String(w.url || "").split("/")[2], pending: w.pending_update_count, last_error: w.last_error_message || "", last_error_at: w.last_error_date ? new Date(w.last_error_date * 1000).toISOString() : "" }; }).catch((e) => String(e)) : "no token";
    extra.ai = await claude({ max_tokens: 5, messages: [{ role: "user", content: "Reply OK" }] }, { job: "health" }).then((r) => ({ ok: true, text: r.text })).catch((e) => ({ ok: false, err: String(e).slice(0, 200) }));
    extra.mail = await mailCheck().catch((e) => ({ ok: false, error: String(e).slice(0, 200) }));
    const tabs = ["Telegram", "Telegram Chat", "Agent Runs", "Agent Approvals", "Tender Projects", "Tender Watches", "Users", "AI Usage", "App Log", "Activity"];
    extra.tabs = Object.fromEntries(await Promise.all(tabs.map(async (t) => [t, await readRanges(ENGINE_SHEET, [`'${t}'!A1:A20000`]).then((v) => (v?.[0]?.length ?? -1)).catch((e) => String(e).slice(0, 120))])));
    extra.env = Object.fromEntries(["GOOGLE_SERVICE_ACCOUNT_JSON", "ANTHROPIC_API_KEY", "TELEGRAM_WEBHOOK_SECRET", "CRON_SECRET", "AUTH_SECRET", "STATE_SHEET_ID", "ZOHO_SMTP_PASS", "AGENT_MODEL", "TG_MODEL"].map((k) => [k, Boolean(process.env[k])]));
  }
  const bad = out.filter((o) => (o.status as number) !== 200 || o.err);
  return NextResponse.json({ ok: !bad.length, deployment: (process.env.VERCEL_DEPLOYMENT_ID || "").slice(-8), checks: out, bad: bad.map((b) => b.name), ...extra });
}
