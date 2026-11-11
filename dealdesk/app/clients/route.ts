import { NextRequest, NextResponse } from "next/server";

// /clients: the client screens live in the panel (dealdesk/public/panel.html, view "clients"), which is the one client
// UI. This address exists so the site navigation and saved links have a stable target; it holds no data of its own.
// The session is checked by the middleware before this runs, and every client API call derives the workspace itself.
export const dynamic = "force-dynamic";
export function GET(req: NextRequest) {
  return NextResponse.redirect(new URL("/#clients", req.url), 307);
}
