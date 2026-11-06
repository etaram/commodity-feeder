import { NextRequest, NextResponse, after } from "next/server";
import { step } from "@/lib/dealagent";
import { agentIo } from "@/lib/telegram";

export const dynamic = "force-dynamic";
export const maxDuration = 300;

// One step of a deal agent run (lib/dealagent.ts). Called only by the agent itself, with the webhook secret; it
// answers at once and does the work after the answer, then chains the next step the same way.
export async function POST(req: NextRequest) {
  const secret = process.env.TELEGRAM_WEBHOOK_SECRET || "";
  if (!secret || req.headers.get("x-agent-secret") !== secret) return NextResponse.json({ ok: false }, { status: 401 });
  const b = await req.json().catch(() => ({}));
  const id = String(b.id || "").slice(0, 40);
  if (!/^AG[A-Z0-9]+$/.test(id)) return NextResponse.json({ ok: false }, { status: 400 });
  after(async () => { await step(agentIo, id, 240_000); });
  return NextResponse.json({ ok: true }, { status: 202 });
}
