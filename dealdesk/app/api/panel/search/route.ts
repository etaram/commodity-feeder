import { NextRequest, NextResponse } from "next/server";
import { searchTenders, searchSuppliers } from "@/lib/panel";
import { gate } from "@/lib/gate";
import { scrubTendersForWs } from "@/lib/scope";

export const dynamic = "force-dynamic";
export const maxDuration = 60;

export async function POST(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const { kind, values } = await req.json().catch(() => ({}));
  try {
    const v = Array.isArray(values) ? values : [];
    const meta: { total?: number } = {};
    const grid = kind === "c" ? await searchSuppliers(v) : scrubTendersForWs(await searchTenders(v, meta), s.ws);
    return NextResponse.json({ ok: true, values: grid, total: meta.total ?? Math.max(0, grid.length - 1) });
  } catch (e) {
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 });
  }
}
