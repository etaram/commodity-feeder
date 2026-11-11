// What the API returns for a mission: the header, and for each task its status, the persona behind its role
// (ROLE_PERSONAS; internal roles have none), a summary of its output and the sources of that output. Pure.
import { personasFor, type Mission } from "@/lib/mission";
import type { TaskOutput } from "@/lib/missionrun";

const cut = (v: unknown, n: number) => String(v ?? "").slice(0, n);
export type TaskView = { key: string; step: string; role: string; persona: string; status: string; attempt: number; review: string; summary: string; sources: string[]; open_questions: string[]; last_error: string };
export type MissionView = { id: string; type: string; goal: string; deal_id: string; status: string; cost_budget_usd: number; spent_usd: number; next_decision: string; tasks: number;
  task_list: TaskView[]; created_at: string; updated_at: string };

export function missionView(m: Mission): MissionView {
  return { id: m.id, type: m.type, goal: m.goal, deal_id: m.deal_id, status: m.status, cost_budget_usd: m.cost_budget_usd, spent_usd: m.spent_usd, next_decision: m.next_decision, tasks: m.tasks.length,
    created_at: m.created_at, updated_at: m.updated_at,
    task_list: m.tasks.map((t) => {
      const o = (t.output && typeof t.output === "object" ? t.output : null) as Partial<TaskOutput> | null, people = personasFor(t.role);
      return { key: t.idempotency_key, step: t.idempotency_key.split(":").pop() || "", role: t.role,
        // several regional personas share one role: none is named until a task is tied to a region
        persona: people.length === 1 ? `${people[0].name}, ${people[0].title}` : people.length ? "regional relations team" : "internal review (no persona)",
        status: t.status, attempt: t.attempt, review: t.reviewer_result ? `${t.reviewer_result.verdict} (${t.reviewer_result.reviewer_role})` : "",
        // an output whose review failed is not shown as a result
        summary: t.status === "completed" ? cut(o?.summary, 600) : "", sources: t.status === "completed" && Array.isArray(o?.sources) ? o!.sources!.slice(0, 8).map((x) => cut(x, 300)) : [],
        open_questions: t.status === "completed" && Array.isArray(o?.open_questions) ? o!.open_questions!.slice(0, 6).map((x) => cut(x, 300)) : [], last_error: cut(t.last_error, 300) };
    }) };
}
