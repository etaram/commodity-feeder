import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { links } from "@/lib/telegram";
import { loadProjects, openProject } from "@/lib/projects";

// One list of bid projects for the panel and the Telegram bot (lib/projects.ts is the single record). GET: the signed-in
// user's projects, with the next step and the deal file. POST {tender_id}: opens the project the same way the bot does
// (schedule back from the deadline, the deal agent starts, the card arrives on the user's own Telegram). Nothing goes to
// suppliers or buyers from here; a user who has not linked Telegram gets code "no_telegram" and the panel keeps its queue.
export const dynamic = "force-dynamic";
export const maxDuration = 120;

async function who(email: string) {
  const l = (await links().catch(() => [])).find((x) => x.email.toLowerCase() === email.toLowerCase());
  return l ? { chat: l.chat_id, email: l.email, name: l.name, lang: l.lang } : null;
}
const view = (p: Awaited<ReturnType<typeof loadProjects>>[number]) => {
  const nx = p.steps.find((s) => !s.done);
  return { id: p.id, tender_id: p.tender_id, title: p.title, buyer: p.buyer, country: p.country, deadline: p.deadline, status: p.status, created: p.created,
    deal_id: p.deal_id, next_step: nx?.k || "", next_due: nx?.due || "", steps_done: p.steps.filter((s) => s.done).length, steps: p.steps.length };
};

export async function GET() {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  try {
    const w = await who(s.email);
    return NextResponse.json({ ok: true, telegram: !!w, projects: w ? (await loadProjects(w.chat)).filter((p) => p.status !== "closed").map(view) : [] });
  } catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}

export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  const tid = String(b.tender_id || "").slice(0, 120);
  if (!tid) return NextResponse.json({ ok: false, error: "tender_id is required" }, { status: 400 });
  try {
    const w = await who(s.email);
    if (!w) return NextResponse.json({ ok: false, code: "no_telegram" });
    await openProject(w, tid);
    const p = (await loadProjects(w.chat)).find((x) => x.tender_id === tid && x.status !== "closed");
    return NextResponse.json({ ok: !!p, project: p ? view(p) : null, code: p ? "" : "not_opened" });
  } catch (e) { return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 500 }); }
}
