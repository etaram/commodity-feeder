import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { findWinners } from "@/lib/index";

export const dynamic = "force-dynamic";
// Fresh contract winners as sales leads: ?q=words&kind=commodity|contractor&country=ISO3&n=50
export async function GET(req: Request) {
  const auth = await gate();
  if (!auth.s) return auth.res;
  const u = new URL(req.url);
  const n = Math.min(200, Math.max(1, Number(u.searchParams.get("n")) || 50));
  return NextResponse.json(await findWinners({ text: u.searchParams.get("q") || "", kind: u.searchParams.get("kind") || "", country: u.searchParams.get("country") || "", n }));
}
