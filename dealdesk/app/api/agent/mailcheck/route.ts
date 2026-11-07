import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { mailCheck } from "@/lib/mailer";

export const dynamic = "force-dynamic";
// Admin check that the agent's mailbox signs in. Sends nothing.
export async function GET() {
  const auth = await gate("admin");
  if (!auth.s) return auth.res;
  return NextResponse.json(await mailCheck());
}
