import { NextResponse } from "next/server";
import { mcpKey } from "@/lib/selfkey";
import { readOnlyTool, readOnlyToolDefs } from "@/lib/dealagent";

// A read-only MCP server (streamable HTTP, stateless JSON-RPC) on the Deal Desk's own data: suppliers, tenders, fresh
// winners, company and buyer footprints, entry routes, logistics directory, deal economics. The address carries a key
// derived from AUTH_SECRET; nothing here writes records or sends messages.
export const dynamic = "force-dynamic";
export const maxDuration = 60;
const PROTOCOL = "2025-06-18";

type Rpc = { jsonrpc: "2.0"; id?: string | number | null; method: string; params?: Record<string, unknown> };
const ok = (id: Rpc["id"], result: unknown) => ({ jsonrpc: "2.0", id, result });
const err = (id: Rpc["id"], code: number, message: string) => ({ jsonrpc: "2.0", id, error: { code, message } });

async function handle(m: Rpc) {
  if (m.method === "initialize") {
    return ok(m.id, { protocolVersion: String((m.params || {}).protocolVersion || PROTOCOL), capabilities: { tools: { listChanged: false } },
      serverInfo: { name: "sinder-deal-desk", version: "1.0.0" },
      instructions: "Read-only access to the Sinder Deal Desk data: supplier index, open tenders, fresh contract winners, company and buyer award footprints, tender entry routes, logistics directory and a deal cash calculator. Needs inferred from contract titles are hypotheses." });
  }
  if (m.method === "ping") return ok(m.id, {});
  if (m.method === "tools/list") return ok(m.id, { tools: readOnlyToolDefs().map((t) => ({ name: t.name, description: t.description, inputSchema: t.input_schema, annotations: { readOnlyHint: true } })) });
  if (m.method === "tools/call") {
    const p = m.params || {};
    try {
      const text = await readOnlyTool(String(p.name || ""), (p.arguments || {}) as Record<string, unknown>);
      return ok(m.id, { content: [{ type: "text", text }], isError: false });
    } catch (e) {
      return ok(m.id, { content: [{ type: "text", text: String(e).slice(0, 300) }], isError: true });
    }
  }
  return err(m.id ?? null, -32601, "method not found");
}

export async function POST(req: Request, ctx: { params: Promise<{ key: string }> }) {
  const want = await mcpKey();
  const { key } = await ctx.params;
  if (!want || key !== want) return NextResponse.json({ error: "not found" }, { status: 404 });
  let body: Rpc | Rpc[];
  try { body = await req.json(); } catch { return NextResponse.json(err(null, -32700, "parse error"), { status: 400 }); }
  const list = Array.isArray(body) ? body : [body];
  const out = [];
  for (const m of list) {
    if (!m || typeof m.method !== "string") { out.push(err(null, -32600, "invalid request")); continue; }
    if (m.id === undefined || m.method.startsWith("notifications/")) continue;   // notifications get no reply
    out.push(await handle(m));
  }
  if (!out.length) return new NextResponse(null, { status: 202 });
  return NextResponse.json(Array.isArray(body) ? out : out[0], { headers: { "MCP-Protocol-Version": PROTOCOL } });
}
export async function GET() { return new NextResponse(null, { status: 405, headers: { Allow: "POST" } }); }
export async function DELETE() { return new NextResponse(null, { status: 405, headers: { Allow: "POST" } }); }
