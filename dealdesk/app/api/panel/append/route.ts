import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { appendRow, sheetsEnabled } from "@/lib/sheets";

// The panel's writes: new research jobs and tracked pursuits. Only these two tabs can be written from the web.
const TABS: Record<string, string> = { "'Panel Jobs'!A1": "Panel Jobs", "'Pursuits'!A1": "Pursuits" };

export async function POST(req: NextRequest) {
  const session = verifySession((await cookies()).get("dd_session")?.value);
  if (!session) return NextResponse.json({ ok: false }, { status: 401 });
  const { range, values } = await req.json().catch(() => ({}));
  const tab = TABS[String(range)];
  if (!tab || !Array.isArray(values) || !Array.isArray(values[0])) return NextResponse.json({ ok: false, error: "not allowed" }, { status: 400 });
  if (!sheetsEnabled()) return NextResponse.json({ ok: false, code: "server_not_connected", error: "Writing to the sheet needs GOOGLE_SERVICE_ACCOUNT_JSON in Vercel" }, { status: 503 });
  try {
    await appendRow(tab, values[0].map((x: unknown) => (typeof x === "number" ? x : String(x ?? "").slice(0, 4000))));
    return NextResponse.json({ ok: true });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
