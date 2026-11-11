import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { mcpKey } from "@/lib/selfkey";
import { ownWorkspace } from "@/lib/scope";

// The MCP server address, for a signed-in admin only. Add it in Claude as a custom connector.
export const dynamic = "force-dynamic";
export async function GET(req: Request) {
  const auth = await gate("admin");
  if (!auth.s) return auth.res;
  // the address reads the original workspace's data (supplier contacts included): its admins only
  if (!ownWorkspace(auth.s.ws)) return NextResponse.json({ ok: false, code: "forbidden", error: "Not available in this workspace" }, { status: 403 });
  const k = await mcpKey();
  if (!k) return NextResponse.json({ ok: false, error: "MCP is disabled" });
  const u = new URL(req.url);
  return NextResponse.json({ ok: true, url: `${u.origin}/api/mcp/${k}`, note: "Keep this address private: it gives read access to the Deal Desk data. Changing AUTH_SECRET revokes it." });
}
