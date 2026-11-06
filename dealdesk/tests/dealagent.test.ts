// Deal agent loop with a scripted model: tools run, ask_owner pauses, an answer resumes, propose_message waits for
// approval and nothing is sent until the owner approves. Build: node tests/build-agent-test.mjs && node <out>
import { startRun, step, loadRun, resume, decide } from "@/lib/dealagent";
import { richText, supplierUrl } from "@/lib/links";
import { TABS } from "./mocks/sheets";
import { SAVED } from "./mocks/deal";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.ANTHROPIC_API_KEY = "test";
const sent: { chat: string; text: string; extra?: Record<string, unknown> }[] = [];
const kicks: string[] = [];
const io = { send: async (chat: string, text: string, extra?: Record<string, unknown>) => { sent.push({ chat, text, extra }); }, kick: async (id: string) => { kicks.push(id); } };
const script: unknown[][] = [
  [{ type: "text", text: "Starting." }, { type: "tool_use", id: "u1", name: "search_suppliers", input: { product: "white maize" } }],
  [{ type: "tool_use", id: "u2", name: "ask_owner", input: { question: "כמה טון?" } }],
  [{ type: "tool_use", id: "u3", name: "supplier_contact", input: { company: "Grain SA", country: "ZAF" } }, { type: "tool_use", id: "u4", name: "tender_routes", input: { tender_id: "T1" } }],
  [{ type: "tool_use", id: "u5", name: "propose_message", input: { to_name: "Grain SA", to_email: "sales@grainsa.co.za", subject: "RFQ white maize", body: "Dear team, ... This is a request for information, not an order.", why: "supported match" } }, { type: "tool_use", id: "u6", name: "deal_economics", input: { sale_price: 1650000, cost_goods: 1400000, freight: 150000, fin_rate_pct: 10, supplier_pay_day: 0, customer_pay_day: 90, funding_limit: 500000 } }],
  [{ type: "tool_use", id: "u7", name: "finish", input: { summary: "נמצא ספק אחד מתאים, פנייה ממתינה לאישור." } }],
];
const seen: { messages: { role: string; content: unknown }[] }[] = [];
(globalThis as { fetch: unknown }).fetch = async (_u: string, init: { body: string }) => {
  const body = JSON.parse(init.body); seen.push(body);
  const content = script.shift() || [{ type: "text", text: "done" }];
  return { ok: true, json: async () => ({ content, stop_reason: "tool_use", usage: { input_tokens: 1000, output_tokens: 200 } }) };
};
(async () => {
  const r = await startRun(io, { chat: "C1", email: "o@x.com", name: "Owner", lang: "he", request: "תמצא לי תירס לבן לקניה" });
  ok(kicks.length === 1 && /^AG/.test(r.id), "a run is created and its first step chained");
  await step(io, r.id, 120_000);
  let cur = (await loadRun(r.id))!;
  ok(cur.status === "waiting" && sent.some((m) => /כמה טון/.test(m.text)), "ask_owner pauses the run and asks in Telegram");
  const res1 = JSON.stringify(seen[1].messages[seen[1].messages.length - 1]);
  ok(res1.includes("Grain SA") && !res1.includes("Filtro"), "incompatible suppliers are removed before the model sees them");
  await resume(io, cur, "5,000 טון");
  cur = (await loadRun(r.id))!;
  ok(cur.status === "running" && JSON.stringify(cur.msgs).includes("The owner answered: 5,000"), "the answer goes back into the paused tool result");
  await step(io, r.id, 120_000);
  cur = (await loadRun(r.id))!;
  ok(cur.status === "done" && sent.some((m) => /סיכום העסקה/.test(m.text)), "the run finishes with a summary in Telegram");
  const appr = sent.find((m) => m.extra && JSON.stringify(m.extra).includes("ag:ok:"));
  ok(!!appr && /RFQ white maize/.test(appr!.text), "the supplier message is shown with Approve and Reject buttons");
  ok((TABS["Agent Approvals"] || []).length === 1 && TABS["Agent Approvals"][0][4] === "pending", "the message is pending, not sent");
  const ctx = JSON.stringify(seen[3].messages);
  ok(ctx.includes("blocked") && ctx.includes("sales@grainsa.co.za"), "routes and the stored contact reach the model");
  const econ = JSON.stringify(seen[4].messages[seen[4].messages.length - 1]);
  ok(/exceeds the limit/.test(econ) && /indicative estimate/.test(econ), "economics come back labelled as an estimate, with the funding warning");
  const id = String(TABS["Agent Approvals"][0][0]);
  const before = sent.length;
  await decide(io, "C2", id, true);
  ok(sent[sent.length - 1].text === "-" && (TABS["Agent Approvals"] || []).length === 1, "another chat cannot approve the message");
  await decide(io, "C1", id, true);
  ok(sent.length === before + 2 && /<pre>/.test(sent[sent.length - 1].text) && TABS["Agent Approvals"][1][4] === "approved", "approval hands the ready message to the owner (no mailbox connected)");
  ok(SAVED.length >= 2, "the deal is saved in the deal records");
  ok(cur.usd > 0 && (TABS["AI Usage"] || []).length === 5, "every model turn is metered");
  ok(richText("ראה [Grain SA](https://desk.sinder.pro/?open=s:Grain%20SA) <b>") === 'ראה <a href="https://desk.sinder.pro/?open=s:Grain%20SA">Grain SA</a> &lt;b&gt;', "model links become Telegram links, other markup is escaped");
  ok(!richText("[x](javascript:alert(1))").includes("<a"), "only http and https links");
  ok(JSON.stringify(seen[1].messages).includes(supplierUrl("Grain SA", "ZAF").replace(/"/g, "")), "supplier rows carry the link to their page");
  const sum = sent.find((m) => /סיכום העסקה/.test(m.text));
  ok(!!sum && JSON.stringify(sum.extra).includes("open=d%3AAGENT-") || JSON.stringify(sum?.extra).includes("open=d:AGENT-"), "the summary has a button to the deal page");
  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})();
