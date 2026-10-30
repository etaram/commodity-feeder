import { NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { markets } from "@/lib/markets";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST() {
  if (!verifySession((await cookies()).get("dd_session")?.value)) return NextResponse.json({ ok: false }, { status: 401 });
  try { return NextResponse.json({ ok: true, ...(await markets() as object) }); }
  catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
