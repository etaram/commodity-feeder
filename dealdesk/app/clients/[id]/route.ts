import { NextRequest, NextResponse } from "next/server";

// /clients/CL-...: opens the panel's client view on that client. The id is only passed on when it has the shape of a
// client id; whether the caller may see it is decided by GET /api/clients/:id (404 for another workspace's client).
export const dynamic = "force-dynamic";
export async function GET(req: NextRequest, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return NextResponse.redirect(new URL(/^CL-[A-Z0-9]{6,24}$/.test(id) ? `/?client=${id}#clients` : "/#clients", req.url), 307);
}
