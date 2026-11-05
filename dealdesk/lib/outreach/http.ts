import { NextRequest, NextResponse } from "next/server";
import { logEvent } from "@/lib/log";

// Small helpers shared by the /api/outreach routes.
export async function body(req: NextRequest): Promise<Record<string, any>> {
  const j = await req.json().catch(() => ({}));
  return j && typeof j === "object" ? (j as Record<string, any>) : {};
}
export const bad = (error: string, status = 400) => NextResponse.json({ ok: false, error }, { status });
export function fail(e: unknown, area = "outreach") {
  const msg = String((e as Error)?.message || e).slice(0, 300);
  const known = /not found|cannot|required|cancelled|is not|must|exceeds|unknown|not an email|no |only /i.test(msg);
  if (!known) void logEvent("error", area, msg);
  return NextResponse.json({ ok: false, error: msg }, { status: /not found/.test(msg) ? 404 : known ? 400 : 500 });
}
export const q = (req: NextRequest, k: string) => (req.nextUrl.searchParams.get(k) || "").slice(0, 80);
