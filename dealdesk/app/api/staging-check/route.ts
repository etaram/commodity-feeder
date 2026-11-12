import { NextResponse } from "next/server";
import { appendRow, appendTo, ENGINE_SHEET, readRanges, sheetFor, sheetsEnabled, stateSheet } from "@/lib/sheets";
import { mailReady } from "@/lib/mailer";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

// Proof that a staging (preview) deployment is separated from the live system. Exists only when VERCEL_ENV=preview, or
// DESK_ENV=server-test (the server copy, deploy/docker-compose.server.yml): on the live site it answers 404. It writes one marked row to the state sheet this deployment uses, tries one write to
// the live engine sheet (which must be refused before any request leaves), and reports the settings without any secret.
export async function GET() {
  if (process.env.VERCEL_ENV !== "preview" && process.env.DESK_ENV !== "server-test") return NextResponse.json({ ok: false }, { status: 404 });
  const tail = (s: string) => (s ? "..." + s.slice(-6) : "");
  const marker = `staging-check ${new Date().toISOString()}`;
  const out: Record<string, unknown> = {
    env: process.env.VERCEL_ENV || process.env.DESK_ENV, deployment: process.env.VERCEL_DEPLOYMENT_ID || "", commit: (process.env.VERCEL_GIT_COMMIT_SHA || "").slice(0, 8),
    sheets_configured: sheetsEnabled(), state_sheet: tail(stateSheet()), engine_sheet: tail(ENGINE_SHEET),
    state_is_engine: stateSheet() === ENGINE_SHEET, suppression_goes_to: tail(sheetFor("Suppression")),
    readonly_ids: (process.env.SHEETS_READONLY_IDS || "").split(",").filter(Boolean).map((x) => tail(x.trim())),
    mail_can_send: mailReady(), marker,
  };
  try { await appendRow("App Log", [marker, "info", "staging", "staging-check write", "", "", "preview"]); out.write_to_state = "written"; }
  catch (e) { out.write_to_state = "FAILED: " + String((e as Error).message || e).slice(0, 160); }
  try {
    const rows = (await readRanges(ENGINE_SHEET, ["'App Log'!A2:A20000"]))?.[0] || [];
    out.read_back_from_state = rows.some((r) => r[0] === marker) ? "marker found" : "marker NOT found";
  } catch (e) { out.read_back_from_state = "FAILED: " + String((e as Error).message || e).slice(0, 160); }
  try { await appendTo(ENGINE_SHEET, "App Log", [marker, "MUST NOT APPEAR IN THE LIVE SHEET"]); out.write_to_live_engine = "NOT REFUSED - STAGING IS NOT SEPARATED"; }
  catch (e) { out.write_to_live_engine = "refused: " + String((e as Error).message || e).slice(0, 120); }
  try { out.engine_data_readable = ((await readRanges(ENGINE_SHEET, ["'Users'!A1:A2"]))?.[0] || []).length >= 0; }
  catch (e) { out.engine_data_readable = "FAILED: " + String((e as Error).message || e).slice(0, 120); }
  out.ok = out.write_to_state === "written" && out.read_back_from_state === "marker found" && String(out.write_to_live_engine).startsWith("refused") && out.mail_can_send === false && !out.state_is_engine;
  return NextResponse.json(out);
}
