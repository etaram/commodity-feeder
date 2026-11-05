import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { generateLinkedInTasks, INTERACTIONS, linkedinTasks, logLinkedInTask, type Interaction } from "@/lib/outreach/linkedin-tasks";
import { bad, body, fail, q } from "@/lib/outreach/http";
import { routeDeps } from "@/lib/outreach";
import type { ReplyCategory } from "@/lib/outreach/types";

export const dynamic = "force-dynamic";

// LinkedIn is a human-executed task queue: nothing here contacts LinkedIn.
// GET ?campaign_id=&status=open  -> { ok, tasks: [{id, kind, status, profile_url, company, contact_name, draft, ...}] }
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const all = linkedinTasks(await routeDeps().store.load(), s.ws, q(req, "campaign_id") || undefined);
    const st = q(req, "status");
    return NextResponse.json({ ok: true, tasks: st ? all.filter((t) => t.status === st) : all });
  } catch (e) { return fail(e); }
}

// POST { action: "generate", campaign_id }  creates prospect / connect / message tasks with approved drafts
// POST { action: "log", task_id, status: "done"|"skipped", interaction, note?, reply_text?, reply_category? }
//   records what the person did by hand; interactions: profile_viewed, connection_sent, connection_accepted,
//   message_sent, reply_received, meeting_booked, not_done
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  try {
    const b = await body(req);
    const d = routeDeps();
    if (b.action === "generate") {
      if (!b.campaign_id) return bad("campaign_id is required");
      const r = await generateLinkedInTasks(d, s.ws, String(b.campaign_id), s.email);
      await logActivity(s, "outreach_linkedin_tasks", String(b.campaign_id), `created ${r.created}`);
      return NextResponse.json({ ok: true, ...r });
    }
    if (b.action === "log") {
      if (!b.task_id) return bad("task_id is required");
      if (!INTERACTIONS.includes(b.interaction)) return bad("unknown interaction");
      const r = await logLinkedInTask(d, s.ws, {
        task_id: String(b.task_id), status: b.status === "skipped" ? "skipped" : "done", interaction: b.interaction as Interaction,
        note: String(b.note || ""), reply_text: String(b.reply_text || "").slice(0, 20000), reply_category: b.reply_category ? (String(b.reply_category) as ReplyCategory) : undefined,
      }, s.email);
      await logActivity(s, "outreach_linkedin_log", String(b.task_id), String(b.interaction));
      return NextResponse.json({ ok: true, ...r });
    }
    return bad("unknown action");
  } catch (e) { return fail(e); }
}
