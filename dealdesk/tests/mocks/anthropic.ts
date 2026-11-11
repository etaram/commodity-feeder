// Model stand-in for tests/isolation.test.ts: no call leaves the process. Every prompt is recorded with the session
// label the test set, so the test can check what text was assembled for the model under each workspace.
export * from "../../lib/anthropic";
export const AI = { who: "", calls: [] as { who: string; prompt: string; job: string }[], reply: (prompt: string) => `ANSWER#${AI.calls.length} ${prompt.slice(0, 0)}` };
export async function claude(body: Record<string, unknown>, meta: { job?: string } = {}) {
  const prompt = JSON.stringify(body);
  AI.calls.push({ who: AI.who, prompt, job: meta.job || "" });
  return { text: AI.reply(prompt), sources: [] as { url: string; title: string }[] };
}
export async function budgetState() { return { spent_usd: 0, alert_usd: 0, over_alert: false, estimated: true }; }
