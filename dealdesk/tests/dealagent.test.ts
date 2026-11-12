// Deal agent loop with a scripted model: tools run, ask_owner pauses, an answer resumes, propose_message waits for
// approval and nothing is sent until the owner approves. Build: node tests/build-agent-test.mjs && node <out>
import { startRun, step, loadRun, resume, decide, recipientTrust, emailsIn, WEB_FLAG, AGENT_NOTE } from "@/lib/dealagent";
import { richText, supplierUrl } from "@/lib/links";
import { TABS } from "./mocks/sheets";
import { MAIL } from "./mocks/mailer";
import { SAVED } from "./mocks/deal";
import { addSuppression } from "@/lib/outreach/suppression";
import { sheetsStore } from "@/lib/outreach/store-sheets";
import { CONTROL_ID } from "@/lib/outreach/campaign";
import { nextRev } from "@/lib/outreach/store";
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
  ok(/exceeds the limit/.test(econ) && /Scenario estimate/.test(econ) && !/Estimate from quotes/.test(econ), "economics come back titled Scenario estimate, with the funding warning");
  ok(/fin_rate_pct[^}]*assumption/.test(econ) && /customer_pay_day[^}]*assumption/.test(econ) && /cost_goods[^}]*assumption/.test(econ), "each input carries its basis: defaults and unlabelled values are assumptions");
  ok(/win_probability[^,]*not calculated/.test(econ) && !/\d+(\.\d+)?\s*%/.test(econ), "no win probability and no percentage in the economics output");
  const id = String(TABS["Agent Approvals"][0][0]);
  const before = sent.length;
  await decide(io, "C2", id, true);
  ok(sent[sent.length - 1].text === "-" && (TABS["Agent Approvals"] || []).length === 1, "another chat cannot approve the message");
  await decide(io, "C1", id, true);
  const ap = () => (TABS["Agent Approvals"] || []).filter((x) => x[0] === id).map((x) => String(x[4]));
  ok(sent.length === before + 2 && /<pre>/.test(sent[sent.length - 1].text) && ap().join() === "pending,send_failed", "without a mailbox the approved message is handed to the owner");
  await decide(io, "C1", id, true);
  ok(/כבר טופל/.test(sent[sent.length - 1].text) && ap().length === 2, "a second press never sends again");
  // with a mailbox: two presses at the same moment send exactly one mail
  MAIL.ready = true;
  TABS["Agent Approvals"].push(["M2", r.id, "C1", new Date().toISOString(), "pending", JSON.stringify({ to_name: "Grain SA", to_email: "sales@grainsa.co.za", subject: "RFQ", body: "b" })]);
  await Promise.all([decide(io, "C1", "M2", true), decide(io, "C1", "M2", true)]);
  const m2 = () => TABS["Agent Approvals"].filter((x) => x[0] === "M2").map((x) => String(x[4]));
  ok(MAIL.sent.length === 1 && m2().join() === "pending,sending,sent", "a double press sends one mail: " + m2().join());
  const party = (SAVED as unknown[][]).filter((x) => x[1] === "party" && x[2] === "PM2").pop();
  ok(!!party && party[4] === "contacted", "the supplier moves to contacted when the request left");
  // a send that never reported back becomes needs_review, and goes out again only on the owner's press
  TABS["Agent Approvals"].push(["M3", r.id, "C1", new Date(Date.now() - 3600e3).toISOString(), "pending", JSON.stringify({ to_name: "X", to_email: "x@x.com", subject: "s", body: "b" })]);
  TABS["Agent Approvals"].push(["M3", r.id, "C1", new Date(Date.now() - 3600e3).toISOString(), "sending", ""]);
  await decide(io, "C1", "M3", true);
  ok(/תיקיית "נשלח"/.test(sent[sent.length - 1].text) && MAIL.sent.length === 1 && JSON.stringify(sent[sent.length - 1].extra).includes("ag:re:M3"), "a stuck send asks the owner instead of sending again");
  await decide(io, "C1", "M3", true, true);
  ok(MAIL.sent.length === 2, "Send again sends it");
  // ---- the send guard on the live path (lib/sendguard.ts)
  const ws = (await loadRun(r.id))!.ws || "sinder";
  const st = (id: string) => TABS["Agent Approvals"].filter((x) => x[0] === id).map((x) => String(x[4])).join();
  const last = () => sent[sent.length - 1];
  const pend = (id: string, to = "sales@grainsa.co.za") => TABS["Agent Approvals"].push([id, r.id, "C1", new Date().toISOString(), "pending", JSON.stringify({ to_name: "Grain SA", to_email: to, subject: "RFQ " + id, body: "body " + id })]);
  // a second click on Approve, one after the other: handled, no second mail
  let n0 = MAIL.sent.length;
  await decide(io, "C1", "M2", true);
  ok(MAIL.sent.length === n0 && /כבר טופל/.test(last().text), "a second Approve on a sent message does not send again");
  // even when the approval's own status row was lost (it reads pending again) the idempotency key stops the second send
  TABS["Agent Approvals"].push(["M2", r.id, "C1", new Date().toISOString(), "pending", ""]);
  await decide(io, "C1", "M2", true);
  ok(MAIL.sent.length === n0 && st("M2").endsWith("pending,sending,sent") && /כבר נשלחה קודם/.test(last().text), "a lost status row cannot cause a second send: the key of the approval id is already sent");
  ok((TABS["Send Guard"] || []).filter((x) => x[2] === "approval:M2").map((x) => x[3]).join() === "reserved,sent" && TABS["Send Guard"].some((x) => x[2] === "approval:M2" && x[8] === "Agent Approvals:M2"), "the send is recorded under the approval id, with the approval reference");
  // opt-out: by address, and by the whole domain
  await addSuppression({ store: sheetsStore(), now: () => Date.now() }, ws, "stop@optout.example", "asked to be removed", "reply", "owner");
  await addSuppression({ store: sheetsStore(), now: () => Date.now() }, ws, "@gone.example", "asked to be removed", "reply", "owner");
  pend("M4", "Stop@OptOut.example"); pend("M5", "anyone@gone.example");
  await decide(io, "C1", "M4", true);
  ok(MAIL.sent.length === n0 && st("M4") === "pending,sending,blocked" && /ביקשו לא לקבל פניות/.test(last().text) && !/<pre>/.test(last().text), "an opted-out recipient: approved, not sent, and not handed over for manual sending");
  await decide(io, "C1", "M5", true);
  ok(MAIL.sent.length === n0 && st("M5") === "pending,sending,blocked", "an opted-out domain blocks the send too");
  await decide(io, "C1", "M4", true, true);
  ok(MAIL.sent.length === n0 && /כבר טופל/.test(last().text), "a blocked message cannot be sent again");
  // emergency stop: nothing leaves, the approval stays open, and it goes out after the stop is cleared
  const control = (status: string) => TABS["Campaigns"] = [...(TABS["Campaigns"] || []), [new Date().toISOString(), ws, "*", CONTROL_ID, nextRev(Date.now()), status, "{}", "owner"]];
  control("engaged"); pend("M6");
  await decide(io, "C1", "M6", true);
  ok(MAIL.sent.length === n0 && st("M6") === "pending,sending,pending" && /עצירת החירום/.test(last().text), "with the emergency stop engaged nothing is sent and the approval stays open");
  control("cleared");
  await decide(io, "C1", "M6", true);
  ok(MAIL.sent.length === n0 + 1 && st("M6").endsWith("sending,sent"), "after the stop is cleared the same approval sends once");
  // a timeout after the message data started: delivery unknown, never "send it yourself", never a silent retry
  n0 = MAIL.sent.length; pend("M7");
  MAIL.fail.push({ ok: false, error: "SMTP timeout", stage: "body" });
  await decide(io, "C1", "M7", true);
  ok(st("M7") === "pending,sending,delivery_unknown" && /תיקיית "נשלח"/.test(last().text) && /אל תשלח אותה ידנית/.test(last().text) && !/<pre>/.test(last().text) && JSON.stringify(last().extra).includes("ag:re:M7"), "a timeout after DATA is delivery_unknown: check Sent first, the text is not handed over for manual sending");
  await decide(io, "C1", "M7", true);
  ok(MAIL.sent.length === n0 && st("M7") === "pending,sending,delivery_unknown" && /תיקיית "נשלח"/.test(last().text), "pressing Approve again on an unknown delivery does not send");
  const party7 = (SAVED as unknown[][]).filter((x) => x[1] === "party" && x[2] === "PM7").pop();
  ok(!!party7 && party7[4] !== "contacted", "the supplier is not marked contacted while delivery is unknown");
  await Promise.all([decide(io, "C1", "M7", true, true), decide(io, "C1", "M7", true, true)]);
  ok(MAIL.sent.length === n0 + 1 && st("M7").endsWith("sending,sent"), "the owner's Send again (after checking Sent) sends exactly one, even on a double press");
  // a definite refusal before DATA: send_failed, the owner may retry after the fix
  n0 = MAIL.sent.length; pend("M8");
  MAIL.fail.push({ ok: false, error: "SMTP 535: authentication failed", stage: "auth" });
  await decide(io, "C1", "M8", true);
  ok(st("M8") === "pending,sending,send_failed" && /<pre>/.test(last().text) && /שום דבר לא יצא/.test(last().text) && JSON.stringify(last().extra).includes("ag:re:M8"), "a refusal before DATA is send_failed: nothing left, with a retry button");
  await decide(io, "C1", "M8", true);
  ok(MAIL.sent.length === n0 && /כבר טופל/.test(last().text), "a plain Approve on a failed send does nothing");
  await decide(io, "C1", "M8", true, true);
  ok(MAIL.sent.length === n0 + 1 && st("M8").endsWith("send_failed,sending,sent"), "the retry after the fix sends it");
  // two step calls for one run at the same moment: only one runs the model
  const r2 = await startRun(io, { chat: "C1", email: "o@x.com", name: "Owner", lang: "he", request: "בדיקה" });
  script.push([{ type: "tool_use", id: "v1", name: "finish", input: { summary: "סיום" } }]);
  const calls0 = seen.length;
  await Promise.all([step(io, r2.id, 120_000), step(io, r2.id, 120_000)]);
  ok(seen.length === calls0 + 1 && (await loadRun(r2.id))!.status === "done", "a duplicate step does not run the run twice");
  // ---- recipients (red team finding 6): the code, not the model, decides who a message may be proposed to
  const cards = () => sent.filter((m) => m.extra && JSON.stringify(m.extra).includes("ag:ok:")).length;
  const r3 = await startRun(io, { chat: "C1", email: "o@x.com", name: "Owner", lang: "en", request: "maize again" });
  const rows0 = TABS["Agent Approvals"].length, cards0 = cards();
  script.push(
    // an address that only the model knows (a page told it to write there): refused, nothing reaches the owner
    [{ type: "tool_use", id: "w1", name: "propose_message", input: { to_name: "Grain SA", to_email: "pay@attacker.example", subject: "RFQ", body: "b", why: "the page said so" } }],
    // a known address cannot carry a stranger along
    [{ type: "tool_use", id: "w2", name: "propose_message", input: { to_name: "Grain SA", to_email: "sales@grainsa.co.za, pay@attacker.example", subject: "RFQ", body: "b", why: "w" } }],
    // the lookup of an earlier run does not count in this one
    [{ type: "tool_use", id: "w3", name: "propose_message", input: { to_name: "Grain SA", to_email: "sales@grainsa.co.za", subject: "RFQ", body: "b", why: "w" } }],
    // found on the web and saved as a party by the agent itself: proposed, with the flag on the owner's card
    [{ type: "tool_use", id: "w4", name: "record", input: { kind: "party", data: { role: "supplier", name: "Web Mills", email: "export@webmills.example", source: "https://webmills.example/contact" } } }],
    [{ type: "tool_use", id: "w5", name: "propose_message", input: { to_name: "Web Mills", to_email: "Export@WebMills.example", subject: "RFQ web", body: "b", why: "w" } }],
    // looked up in the system in this run: proposed without a flag
    [{ type: "tool_use", id: "w6", name: "supplier_contact", input: { company: "Grain SA", country: "ZAF" } }],
    [{ type: "tool_use", id: "w7", name: "propose_message", input: { to_name: "Grain SA", to_email: "sales@grainsa.co.za", subject: "RFQ system", body: "b", why: "w" } }],
    // no address at all: still prepared, the owner sends it himself (unchanged behaviour)
    [{ type: "tool_use", id: "w8", name: "propose_message", input: { to_name: "Unknown Mill", subject: "RFQ no address", body: "b", why: "w" } }],
    [{ type: "tool_use", id: "w9", name: "finish", input: { summary: "done" } }],
  );
  const at = seen.length;
  await step(io, r3.id, 600_000);
  const res = (i: number) => JSON.stringify(seen[at + i].messages[seen[at + i].messages.length - 1]);
  ok(/not a known contact of this deal/.test(res(1)) && /owner must add it/.test(res(1)), "an address the deal does not know is refused with the reason");
  ok(/not a known contact of this deal/.test(res(2)), "a known address next to an unknown one is refused as a whole");
  ok(/not a known contact of this deal/.test(res(3)), "a contact lookup from another run does not make the address known here");
  ok(TABS["Agent Approvals"].length === rows0 + 3 && cards() === cards0 + 3, "refused recipients create no approval request and no card: " + (TABS["Agent Approvals"].length - rows0));
  const webCard = sent.find((m) => /RFQ web/.test(m.text)), sysCard = sent.find((m) => /RFQ system/.test(m.text)), noAddr = sent.find((m) => /RFQ no address/.test(m.text));
  ok(!!webCard && webCard!.text.includes(WEB_FLAG) && JSON.stringify(webCard!.extra).includes("ag:ok:"), "a web-found address is proposed with the visible flag: " + WEB_FLAG);
  ok(TABS["Agent Approvals"].some((x) => String(x[5]).includes("RFQ web") && JSON.parse(String(x[5])).unverified === WEB_FLAG), "the flag is stored with the approval request");
  ok(/found on the web/.test(res(5)), "the model is told the owner sees the flag");
  ok(!!sysCard && !sysCard!.text.includes(WEB_FLAG) && (await loadRun(r3.id))!.known!.includes("sales@grainsa.co.za"), "an address from the system lookup in this run is proposed without a flag and kept in the run state");
  ok(!!noAddr && !noAddr!.text.includes(WEB_FLAG), "a message without an address is still prepared for the owner");
  ok((await loadRun(r3.id))!.status === "done", "the run goes on after a refused recipient");
  // the rule itself, as a pure function
  const human = { status: "candidate", data: { email: "Buyer@Ncpb.example; second@ncpb.example" }, note: "" }, agent = { status: "candidate", data: { email: "export@webmills.example" }, note: AGENT_NOTE };
  ok(recipientTrust("buyer@ncpb.example", [], [human]) === "known" && recipientTrust("SECOND@ncpb.example", [], [human]) === "known", "a party a person saved is known (any letter case, several addresses in one field)");
  ok(recipientTrust("export@webmills.example", [], [agent]) === "web" && recipientTrust("export@webmills.example", [], [{ ...agent, note: "approved by the owner" }]) === "known", "a party the agent saved is web-only until the owner approved it");
  ok(recipientTrust("export@webmills.example", ["export@webmills.example"], [agent]) === "known", "the system lookup outranks the agent's own record");
  ok(recipientTrust("buyer@ncpb.example, export@webmills.example", [], [human, agent]) === "web" && recipientTrust("buyer@ncpb.example; x@evil.example", [], [human, agent]) === "unknown", "the weakest address decides");
  ok(recipientTrust("buyer@ncpb.example", [], [{ ...human, status: "dropped" }]) === "unknown" && recipientTrust("buyer@ncpb.example", [], [{ ...human, status: "deleted" }]) === "unknown", "a dropped or deleted party is not a contact");
  ok(recipientTrust("not an address", ["a@b.example"], []) === "unknown" && recipientTrust("a@b.example\nBcc: x@evil.example", ["a@b.example"], []) === "unknown" && recipientTrust("a@b.example extra", ["a@b.example"], []) === "unknown", "anything that is not only addresses is refused");
  ok(recipientTrust("buyer@ncpb.example.evil.example", [], [human]) === "unknown" && recipientTrust("xbuyer@ncpb.example", [], [human]) === "unknown", "a look-alike address is not the known one");
  ok(emailsIn("Sales <a@b.example>; A@B.example, c@d.example").join() === "a@b.example,c@d.example", "addresses are read case-insensitively and once");
  ok(SAVED.length >= 2, "the deal is saved in the deal records");
  ok(cur.usd > 0 && (TABS["AI Usage"] || []).length === seen.length, "every model turn is metered");
  ok(richText("ראה [Grain SA](https://desk.sinder.pro/?open=s:Grain%20SA) <b>") === 'ראה <a href="https://desk.sinder.pro/?open=s:Grain%20SA">Grain SA</a> &lt;b&gt;', "model links become Telegram links, other markup is escaped");
  ok(!richText("[x](javascript:alert(1))").includes("<a"), "only http and https links");
  ok(JSON.stringify(seen[1].messages).includes(supplierUrl("Grain SA", "ZAF").replace(/"/g, "")), "supplier rows carry the link to their page");
  const sum = sent.find((m) => /סיכום העסקה/.test(m.text));
  ok(!!sum && JSON.stringify(sum.extra).includes("open=d%3AAGENT-") || JSON.stringify(sum?.extra).includes("open=d:AGENT-"), "the summary has a button to the deal page");
  // outcome ledger (lib/outcomelog.ts): one rfq_authorized and one rfq_sent per approval that the guard reported as sent
  const led = (TABS["Outcomes"] || []).map((x) => JSON.parse(String(x[6])) as { type: string; case_id: string; proof: { kind: string; id: string }; actor: string; workspace: string });
  const sentIds = [...new Set((TABS["Agent Approvals"] || []).filter((x) => x[4] === "sent" && JSON.parse(String(x[5])).mail_id).map((x) => String(x[0])))];
  const auth = led.filter((e) => e.type === "rfq_authorized"), out = led.filter((e) => e.type === "rfq_sent");
  ok(sentIds.length >= 3 && auth.length === sentIds.length && out.length === sentIds.length && sentIds.every((i) => auth.filter((e) => e.proof.id === `Agent Approvals:${i}`).length === 1),
    `the ledger has rfq_authorized and rfq_sent once for each of the ${sentIds.length} sent approvals, with the approval id as proof`);
  ok(out.every((e) => e.proof.kind === "message" && e.proof.id === "<id@x>" && e.case_id === cur.deal_id && e.actor === "o@x.com" && e.workspace === "sinder") && !auth.some((e) => /:(M4|M5)$/.test(e.proof.id)),
    "rfq_sent carries the mailer's message id; a blocked (opted-out) message writes no event");
  // ---- F14 at the moment of dispatch: who pressed, what was approved, and a right taken away before the send
  let allowed = true; const asked: string[] = [];
  const io2 = { ...io, approver: async (e: string) => { asked.push(e); return allowed; } };
  const orig = { to_name: "Grain SA", to_email: "f14-a@example.test", subject: "F14 original", body: "original body" };
  TABS["Agent Approvals"].push(["M9", r.id, "C1", new Date().toISOString(), "pending", JSON.stringify(orig)]);
  // a later row under the same approval id with another recipient and body (a change after the message was shown)
  TABS["Agent Approvals"].push(["M9", r.id, "C1", new Date().toISOString(), "pending", JSON.stringify({ ...orig, to_email: "f14-changed@example.test", subject: "F14 changed", body: "changed body" })]);
  const n9 = MAIL.sent.length;
  allowed = false;
  await decide(io2, "C1", "M9", true, false, "presser@x.com");
  ok(MAIL.sent.length === n9 && st("M9") === "pending,pending" && asked.join() === "presser@x.com", "approval right taken away before dispatch: nothing sent, nothing recorded as sending, and the presser is the one checked");
  allowed = true;
  await decide(io2, "C1", "M9", true, false, "presser@x.com");
  const m9 = MAIL.sent.slice(n9);
  ok(m9.length === 1 && m9[0].to === "f14-a@example.test" && m9[0].subject === "F14 original", "what leaves is the message that was shown for approval; a later change of recipient or text is not sent");
  const g9 = (TABS["Send Guard"] || []).filter((x) => x[2] === "approval:M9");
  ok(g9.length > 0 && g9.every((x) => x[7] === "presser@x.com") && !g9.some((x) => x[7] === "o@x.com"), "the send record names the person who pressed approve, not the account that started the run");
  // a stuck send, then the right is taken away: Send again does not pass
  TABS["Agent Approvals"].push(["M10", r.id, "C1", new Date(Date.now() - 3600e3).toISOString(), "pending", JSON.stringify({ ...orig, to_email: "f14-b@example.test" })]);
  TABS["Agent Approvals"].push(["M10", r.id, "C1", new Date(Date.now() - 3600e3).toISOString(), "sending", ""]);
  await decide(io2, "C1", "M10", true, false, "presser@x.com");
  allowed = false;
  const n10 = MAIL.sent.length;
  await decide(io2, "C1", "M10", true, true, "presser@x.com");
  ok(MAIL.sent.length === n10, "Send again after the right was taken away sends nothing");
  allowed = true;
  await decide(io2, "C1", "M10", true, true, "presser@x.com");
  ok(MAIL.sent.length === n10 + 1 && MAIL.sent[n10].to === "f14-b@example.test", "with the right back, Send again sends once");
  await decide(io2, "C1", "M9", false, false, "presser@x.com");
  ok(MAIL.sent.length === n10 + 1, "a reject press on an already sent message changes nothing");
  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})();
