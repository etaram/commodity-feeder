import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { hasRole } from "@/lib/auth";
import { appendRow, sheetsEnabled } from "@/lib/sheets";
import { logActivity } from "@/lib/activity";
import { canWriteOwnerTabs } from "@/lib/scope";

// The panel's writes: new research jobs and tracked pursuits. Only these two tabs can be written from the web.
// Analysts and admins may write; approving a project action or closing a project is for admins only.
const TABS: Record<string, string> = { "'Panel Jobs'!A1": "Panel Jobs", "'Pursuits'!A1": "Pursuits" };
const ADMIN_JOBS = new Set(["approval", "project_close"]);

export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  if (!canWriteOwnerTabs(s.ws)) return NextResponse.json({ ok: false, code: "forbidden", error: "These records belong to another workspace" }, { status: 403 });
  const { range, values } = await req.json().catch(() => ({}));
  const tab = TABS[String(range)];
  if (!tab || !Array.isArray(values) || !Array.isArray(values[0])) return NextResponse.json({ ok: false, error: "not allowed" }, { status: 400 });
  const row = values[0].map((x: unknown) => (typeof x === "number" ? x : String(x ?? "").slice(0, 4000)));
  if (tab === "Panel Jobs" && ADMIN_JOBS.has(String(row[2])) && !hasRole(s, "admin")) {
    return NextResponse.json({ ok: false, code: "forbidden", error: "Only an admin can approve or close a project" }, { status: 403 });
  }
  if (!sheetsEnabled()) return NextResponse.json({ ok: false, code: "server_not_connected", error: "Writing to the sheet needs GOOGLE_SERVICE_ACCOUNT_JSON in Vercel" }, { status: 503 });
  try {
    // Column L (notes) records who queued the job, so the worker and the log show a person, not a shared account.
    if (tab === "Panel Jobs") row[11] = `${String(row[11] ?? "")}; by=${s.email}`.slice(0, 300);
    await appendRow(tab, row);
    await logActivity(s, tab === "Panel Jobs" ? "queue_" + String(row[2] || "job") : "pursuit", String(row[4] || row[1] || ""), String(row[6] || "").slice(0, 300));
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
