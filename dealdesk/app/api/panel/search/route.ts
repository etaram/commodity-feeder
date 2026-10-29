import { NextRequest, NextResponse } from "next/server";
import { searchTenders, searchSuppliers } from "@/lib/panel";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  const { kind, values } = await req.json().catch(() => ({}));
  try {
    const v = Array.isArray(values) ? values : [];
    return NextResponse.json({ ok: true, values: kind === "c" ? await searchSuppliers(v) : await searchTenders(v) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
