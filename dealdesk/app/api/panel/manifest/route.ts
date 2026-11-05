import { NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { MATCH_VERSION } from "@/lib/supmatch";
import { MODEL } from "@/lib/anthropic";

// Deployment manifest: what this build runs, so a rollback restores compatible behaviour, not only an old screen.
export const dynamic = "force-dynamic";
export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  return NextResponse.json({ ok: true, manifest: {
    commit: process.env.VERCEL_GIT_COMMIT_SHA || "local", deployment: process.env.VERCEL_DEPLOYMENT_ID || "",
    processing: { supplier_match: MATCH_VERSION, model: MODEL },
    flags: { SUPPLIER_EXPAND: process.env.SUPPLIER_EXPAND || "on", SUPPLIER_STRICT: process.env.SUPPLIER_STRICT || "on", SUPPLIER_VERIFIED: process.env.SUPPLIER_VERIFIED || "on",
      VERIFY_PER_RUN: process.env.VERIFY_PER_RUN || "8", OUTREACH_ENABLED: process.env.OUTREACH_ENABLED ? "set" : "unset" },
    schema: { "Users": "A-M (M workspace)", "Deal Records": "A-K (K workspace)", "Verified capabilities": "supplier, country, product, label, evidence_url, evidence_note, checked, method, source_query" },
  } });
}
