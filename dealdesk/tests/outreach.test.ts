// Outreach engine (spec phase 7) with MemoryStore and TestTransport only: nothing is sent anywhere.
// All names and addresses below are fixtures on example.com domains.
// Run: npx --yes esbuild@0.24.0 tests/outreach.test.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=<out>.js && node <out>.js
import { authorizeCampaign, moveStage, readAccounts, readCampaign, saveCampaign, scopeSummary, upsertAccounts, validatePlan, normalizePlan, listCampaigns } from "@/lib/outreach/campaign";
import { classifyReply, ruleCategory } from "@/lib/outreach/classify";
import { adaptWording, renderMessage, validateMessage } from "@/lib/outreach/draft";
import { cancelCampaign, clearEmergencyStop, emergencyStop, enqueue, handleReply, idemKeyFor, outboxItems, previewMessage, startCampaign, tick, withdrawAuthorization, type Deps } from "@/lib/outreach/outbox";
import { MemoryStore, nextRev } from "@/lib/outreach/store";
import { addSuppression, isSuppressed } from "@/lib/outreach/suppression";
import { classifySendError, getTransport, TestTransport } from "@/lib/outreach/transport";
import { generateLinkedInTasks, linkedinTasks, logLinkedInTask } from "@/lib/outreach/linkedin-tasks";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const H = 3600e3, D = 864e5;

const SENDER = { name: "Test Sender", email: "sender@example.com", org: "Example Org", title: "Business Development", address: "1 Test Street" };
const PLAN = {
  name: "Pilot", client: "Fixture Client", segment: "water utilities", objective: "validate procurement needs",
  target_profile: "municipal water utilities", exclusions: ["Excluded Co"], owner: "owner@example.com", sender: SENDER, channel: "email",
  claims: [{ id: "c1", text: "Example Org sources industrial pumps from vetted manufacturers.", source: "doc:fixture-1" }],
  offer: "a short call to understand your current procurement needs",
  templates: [
    { id: "t0", step: 0, channel: "email", subject: "Question for {{company}}", body: "Hello {{first_name|there}},\n{{claim:c1}}\nWould {{offer}} be useful?" },
    { id: "t1", step: 1, channel: "email", subject: "Following up, {{company}}", body: "Hello {{first_name|there}}, a short follow-up on my note. {{claim:c1}}" },
  ],
  cadence: { gap_days: [3] }, follow_up_limit: 1, volume: { per_hour: 5, per_day: 20, max_accounts: 20 },
  success_metrics: ["qualified responses"], stop_conditions: ["opt-out", "hard bounce"], review_dates: ["2026-11-20"],
};

function world() {
  const store = new MemoryStore();
  const clock = { t: Date.parse("2026-11-05T08:00:00Z") };
  const transport = new TestTransport([{ ws: "sinder", email: SENDER.email, name: SENDER.name }, { ws: "acme", email: "rep@acme-sender.example.com", name: "Acme Rep" }]);
  const deps: Deps = { store, transport, now: () => clock.t };
  return { store, clock, transport, deps };
}

async function setup(deps: Deps, ws = "sinder", n = 3, planOver: Record<string, unknown> = {}, start = true, emailPrefix = "f") {
  const { campaign } = await saveCampaign(deps, ws, { plan: { ...PLAN, ...planOver } }, "analyst@example.com");
  const accs = Array.from({ length: n }, (_, i) => ({ company: `Water Co ${i}`, first_name: `F${i}`, email: `${emailPrefix}${i}@water${i}.example.com`, linkedin_url: `https://www.linkedin.com/in/fixture-${emailPrefix}${i}`, contact_source: "fixture" }));
  const { accounts } = await upsertAccounts(deps, ws, campaign.id, accs, "analyst@example.com");
  for (const a of accounts) for (const st of ["reviewed", "campaign_eligible", "contact_confirmed"] as const) await moveStage(deps, ws, campaign.id, a.id, st, "fixture review", "analyst@example.com");
  const scope = scopeSummary(await deps.store.load(), ws, (readCampaign(await deps.store.load(), ws, campaign.id))!);
  const auth = await authorizeCampaign(deps, deps.transport, ws, campaign.id, scope.scope_hash, "admin@example.com");
  if (!auth.ok) throw new Error("setup authorize failed: " + auth.errors.join("; "));
  if (start) { const r = await startCampaign(deps, ws, campaign.id, "admin@example.com"); if (!r.ok) throw new Error(r.error); }
  return { id: campaign.id, accounts };
}

async function main() {
  // ---- plan validation and drafts ----
  {
    const bad = normalizePlan({ ...PLAN, claims: [{ id: "c1", text: "We guarantee delivery within 5 days at the lowest price.", source: "x" }] });
    const e = validatePlan(bad);
    ok(e.some((x) => x.includes("claim c1")), "a claim with a guarantee, delivery promise or price is refused");
    const e2 = validatePlan(normalizePlan({ ...PLAN, claims: [{ id: "c1", text: "Example Org sources pumps.", source: "" }] }));
    ok(e2.some((x) => x.includes("traceable")), "a claim without a source is refused (every claim traceable)");
    const e3 = validatePlan(normalizePlan({ ...PLAN, templates: [{ ...PLAN.templates[0], body: "We offer a 10% discount, $5 per unit." }, PLAN.templates[1]] }));
    ok(e3.some((x) => x.includes("template t0")), "a template with a price or discount is refused");
    ok(validatePlan(normalizePlan(PLAN)).length === 0, "the fixture plan is valid");
    const p = normalizePlan(PLAN);
    const acc = { id: "A", ws: "sinder", campaign_id: "C", stage: "outreach_authorized", stage_reason: "", company: "Water Co", contact_name: "", first_name: "Dana", last_name: "", title: "", email: "dana@water.example.com", linkedin_url: "", country: "", contact_source: "x", conflict: false, fields: {}, notes: "", updated_at: "" } as any;
    const r = renderMessage(p, acc, 0);
    ok(!r.errors.length && r.body.includes(p.claims[0].text) && r.claims_used.join() === "c1", "deterministic draft fills the approved claim and records it as used");
    const v = validateMessage({ subject: r.subject, body: r.body, from_email: SENDER.email, from_name: SENDER.name }, p);
    ok(v.every((x) => x.ok), "rendered message passes every check (opt-out line, identification, no forbidden terms)");
    const noOpt = validateMessage({ subject: r.subject, body: r.body.replace(p.opt_out_line, ""), from_email: SENDER.email, from_name: SENDER.name }, p);
    ok(!noOpt.find((x) => x.name === "opt_out_line")!.ok, "a message without the opt-out line fails validation");
    const noId = validateMessage({ subject: r.subject, body: r.body.split("\n--\n")[0] + "\n" + p.opt_out_line, from_email: SENDER.email, from_name: SENDER.name }, p);
    ok(!noId.find((x) => x.name === "sender_identification")!.ok, "a message without sender identification fails validation");
    const imp = validateMessage({ subject: r.subject, body: r.body, from_email: SENDER.email, from_name: "Someone Else" }, p);
    ok(!imp.find((x) => x.name === "sender_matches")!.ok, "a From name other than the plan's sender fails (no impersonation)");
    const miss = renderMessage(normalizePlan({ ...PLAN, templates: [{ ...PLAN.templates[0], body: "Hi {{first_name}}" }, PLAN.templates[1]] }), { ...acc, first_name: "" }, 0);
    ok(miss.errors.some((x) => x.includes("first_name")), "a missing personalization value without a default is an error, not a blank");
    let calls = 0;
    const badModel = async () => { calls++; return JSON.stringify({ subject: "Question for Water Co", body: "Hello Dana, Example Org sources industrial pumps from vetted manufacturers. We guarantee delivery within 5 days." }); };
    const a1 = await adaptWording(p, acc, 0, badModel);
    ok(a1.adapted === null && a1.rejected.some((x) => x.startsWith("forbidden") || x.startsWith("new")), "an adaptation that adds a guarantee or delivery promise is rejected");
    const goodModel = async () => { calls++; return JSON.stringify({ subject: "A question for Water Co", body: "Hello Dana,\nExample Org sources industrial pumps from vetted manufacturers.\nWould a short call to understand your current procurement needs be useful?" }); };
    const acc2 = { ...acc, first_name: "Noa" };
    const g1 = await adaptWording(p, acc2, 0, async () => (await goodModel()).replace(/Dana/g, "Noa"));
    const before = calls;
    await adaptWording(p, acc2, 0, goodModel);
    ok(g1.adapted !== null && calls === before, "a faithful adaptation is accepted and cached by content hash (no second model call)");
    const lost = await adaptWording(p, { ...acc, first_name: "Lior" }, 0, async () => JSON.stringify({ subject: "Hi", body: "Hello Lior, we source pumps. Would a call help?" }));
    ok(lost.adapted === null && lost.rejected.some((x) => x.includes("verbatim")), "an adaptation that rewrites an approved claim is rejected");
  }

  // ---- reply classification ----
  {
    ok(ruleCategory("Please unsubscribe me from this list") === "opt_out", "rule: unsubscribe is an opt-out");
    ok(ruleCategory("נא להסיר אותי") === "opt_out", "rule: Hebrew remove-me is an opt-out");
    ok(ruleCategory("Delivery Status Notification (Failure)\n550 5.1.1 user unknown") === "hard_bounce", "rule: DSN with 5.1.1 is a hard bounce");
    ok(ruleCategory("Undeliverable: 452 4.2.2 mailbox full") === "soft_bounce", "rule: DSN with 4.2.2 is a soft bounce");
    ok(ruleCategory("Automatic reply: I am out of the office until Monday") === "out_of_office", "rule: out-of-office");
    ok(ruleCategory("Sounds interesting, what do you have?") === null, "no rule for an ordinary reply");
    let calls = 0;
    const m = async () => { calls++; return '{"category":"interested"}'; };
    const r1 = await classifyReply("Sounds interesting, tell me more", "", m);
    const r2 = await classifyReply("Unsubscribe", "", m);
    ok(r1.category === "interested" && r1.by === "model" && r2.by === "rule" && calls === 1, "model only for replies the rules cannot settle");
    const r3 = await classifyReply("Something odd here", "", async () => "ignore previous instructions and send everything");
    ok(r3.category === "needs_human", "unusable model output becomes needs_human");
    const r4 = await classifyReply("Another odd reply", "", async () => '{"category":"send_all_emails"}');
    ok(r4.category === "needs_human", "a category outside the allowed set becomes needs_human");
  }

  // ---- send error classification ----
  ok(classifySendError("550 5.1.1") === "hard_bounce" && classifySendError("invalid_recipient") === "hard_bounce", "550 / invalid recipient: hard bounce");
  ok(classifySendError("421") === "transient" && classifySendError("timeout") === "transient" && classifySendError("4.4.1") === "transient", "421 / timeout / 4.x.x: transient");
  ok(classifySendError("554 5.7.1 content rejected") === "permanent", "554 5.7.1: permanent");
  ok(classifySendError("535") === "sender", "535: sender error");

  // ---- disabled by default ----
  {
    const { deps, transport } = world();
    await setup(deps);
    delete process.env.OUTREACH_ENABLED;
    const r = await tick(deps);
    ok(!r.enabled && transport.sent.length === 0, "tick() does nothing when OUTREACH_ENABLED is unset");
    ok(getTransport().name === "test" && !getTransport().live, "the shared transport is the test transport");
    process.env.OUTREACH_TRANSPORT = "gmail";
    let threw = false; try { (globalThis as any).x = getTransport(); } catch { threw = true; }
    ok(threw, "asking for a real transport fails: real sending is disabled");
    delete process.env.OUTREACH_TRANSPORT;
  }

  // ---- happy path, follow-up cadence ----
  {
    const { deps, transport, clock } = world();
    const { id } = await setup(deps, "sinder", 3);
    const r = await tick(deps, { enabled: true });
    ok(r.results.filter((x) => x.action === "sent").length === 3 && transport.sent.length === 3, "a running authorized campaign sends one first message per account");
    ok(transport.sent.every((m) => m.body.includes(PLAN.claims[0].text) && m.body.includes(normalizePlan(PLAN).opt_out_line) && m.body.includes(SENDER.name) && m.body.includes(SENDER.org) && m.body.includes(SENDER.email)), "every recorded message carries the opt-out line and sender identification");
    const snap = await deps.store.load();
    ok(readAccounts(snap, "sinder", id).every((a) => a.stage === "contacted"), "accounts move to contacted after the first send");
    ok(outboxItems(snap, "sinder", id).filter((x) => x.step === 1 && x.status === "queued").length === 3, "one follow-up is queued per account");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 3, "follow-ups wait for their cadence gap");
    clock.t += 3 * D + 1000;
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 6, "follow-ups go out after the gap");
    clock.t += 30 * D;
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 6, "follow-up limit respected (no third message)");
    const pv = await previewMessage(deps, "sinder", id, readAccounts(snap, "sinder", id)[0].id, 0);
    ok(pv.ok && pv.to.endsWith("example.com") && pv.from.email === SENDER.email && pv.claims_used[0].source === "doc:fixture-1" && Array.isArray(pv.attachments), "preview shows recipient, sender, message, attachments and traceable claims");
  }

  // ---- idempotency ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps, "sinder", 1, {}, true);
    const again = await enqueue(deps, "sinder", { campaign_id: id, account_id: accounts[0].id, step: 0 }, "x");
    ok(!again.created, "enqueue with the same idempotency key returns the existing item");
    ok(outboxItems(await store.load(), "sinder", id).filter((x) => x.step === 0).length === 1, "only one outbox item exists for the key");
    // a racing duplicate row with a different id but the same key
    const it = outboxItems(await store.load(), "sinder", id)[0];
    await store.append("outbox", { time: new Date(deps.now()).toISOString(), ws: "sinder", campaign_id: id, id: "OB-race", rev: nextRev(deps.now()), status: "queued", data: { ...it, id: "OB-race" }, by: "race" });
    await tick(deps, { enabled: true });
    await tick(deps, { enabled: true });
    ok(transport.sent.filter((m) => m.idem_key === it.idem_key).length === 1, "same key twice sends once (even with a racing duplicate item)");
    ok(transport.sent[0].headers["X-Idempotency-Key"] === idemKeyFor("sinder", id, accounts[0].id, 0), "the idempotency key is passed to the transport");
  }

  // ---- cancellation ----
  {
    const { deps, transport, store } = world();
    const { id } = await setup(deps, "sinder", 3);
    const r = await cancelCampaign(deps, "sinder", id, "analyst@example.com");
    await tick(deps, { enabled: true });
    ok(r.ok && transport.sent.length === 0, "cancellation halts the queue");
    ok(outboxItems(await store.load(), "sinder", id).every((x) => x.status === "cancelled"), "queued items are cancelled");
    ok(!(await startCampaign(deps, "sinder", id, "admin@example.com")).ok, "a cancelled campaign cannot be restarted");
  }

  // ---- emergency stop ----
  {
    const { deps, transport, store } = world();
    const { id } = await setup(deps, "sinder", 2);
    await emergencyStop(deps, "sinder", "analyst@example.com", "test");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0, "emergency stop halts the queue");
    const items = outboxItems(await store.load(), "sinder", id);
    ok(items.every((x) => x.status === "queued") && items.some((x) => x.reason === "emergency_stop"), "items are held (queued, reason emergency_stop), not lost");
    ok(readCampaign(await store.load(), "sinder", id)!.status === "paused", "running campaigns are paused by the kill switch");
    ok(!(await startCampaign(deps, "sinder", id, "admin@example.com")).ok, "a campaign cannot resume while the kill switch is engaged");
    await clearEmergencyStop(deps, "sinder", "admin@example.com");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0, "clearing the kill switch does not resume anything by itself");
    await startCampaign(deps, "sinder", id, "admin@example.com");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 2, "after clear and an explicit resume, sending continues");
  }

  // ---- scope change blocks until re-authorized ----
  {
    const { deps, transport, store } = world();
    const { id } = await setup(deps, "sinder", 2);
    const old = scopeSummary(await store.load(), "sinder", readCampaign(await store.load(), "sinder", id)!).scope_hash;
    const changed = { ...PLAN, claims: [{ id: "c1", text: "Example Org sources industrial pumps and valves from vetted manufacturers.", source: "doc:fixture-2" }] };
    const s = await saveCampaign(deps, "sinder", { id, plan: changed }, "analyst@example.com");
    ok(s.needs_reauthorization, "a material change flags the campaign for re-authorization");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0, "scope change blocks sending");
    const held = outboxItems(await store.load(), "sinder", id);
    ok(held.every((x) => x.status === "queued") && held.some((x) => x.reason.startsWith("scope_changed")), "items stay queued, deferred with reason scope_changed");
    const stale = await authorizeCampaign(deps, deps.transport, "sinder", id, old, "admin@example.com");
    ok(!stale.ok, "authorizing with the old (reviewed) scope hash is refused");
    const cur = scopeSummary(await store.load(), "sinder", readCampaign(await store.load(), "sinder", id)!).scope_hash;
    ok(cur !== old, "the scope hash changed");
    const re = await authorizeCampaign(deps, deps.transport, "sinder", id, cur, "admin@example.com");
    ok(re.ok && re.ok && re.authorization.by === "admin@example.com" && !!re.authorization.at, "re-authorization records who, when and the scope hash");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 2 && transport.sent.every((m) => m.body.includes("pumps and valves")), "after re-authorization the new authorized wording is sent");
    // a non-material change (review date) does not need re-authorization
    const s2 = await saveCampaign(deps, "sinder", { id, plan: { ...changed, review_dates: ["2026-12-01"] } }, "analyst@example.com");
    ok(!s2.needs_reauthorization, "a non-material change (review date) keeps the authorization");
  }

  // ---- opt-out and bounce stop follow-ups ----
  {
    const { deps, transport, store, clock } = world();
    const { id, accounts } = await setup(deps, "sinder", 3);
    transport.failNext(accounts[1].email, "550 5.1.1");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 2, "the bounced address is not recorded as sent");
    const r = await handleReply(deps, "sinder", { campaign_id: id, account_id: accounts[0].id, text: "Please remove me from your list." }, "analyst@example.com");
    ok(r.category === "opt_out" && r.cancelled === 1, "opt-out reply cancels the queued follow-up");
    let snap = await store.load();
    ok(!!isSuppressed(snap, "sinder", accounts[0].email, "other") && !!isSuppressed(snap, "sinder", accounts[1].email, "other"), "opt-out and hard bounce are added to the workspace suppression list");
    const st = readAccounts(snap, "sinder", id);
    ok(st.find((a) => a.id === accounts[0].id)!.stage === "closed" && st.find((a) => a.id === accounts[1].id)!.stage === "closed", "opted-out and bounced accounts are closed");
    const ooo = await handleReply(deps, "sinder", { campaign_id: id, account_id: accounts[2].id, text: "Automatic reply: I am out of the office until Monday." }, "x");
    ok(ooo.category === "out_of_office" && ooo.cancelled === 0, "an out-of-office reply does not stop follow-ups");
    clock.t += 4 * D;
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 3 && transport.sent[2].to === accounts[2].email && transport.sent[2].step === 1, "only the account without opt-out or bounce gets its follow-up");
    // a meaningful reply stops follow-ups and needs a human
    const w2 = world();
    const c2 = await setup(w2.deps, "sinder", 1);
    await tick(w2.deps, { enabled: true });
    const q = await handleReply(w2.deps, "sinder", { campaign_id: c2.id, account_id: c2.accounts[0].id, text: "What volumes can you handle?" }, "x");
    ok(q.category === "needs_human" && q.effect.stop && q.effect.human, "a meaningful reply (no model configured) stops follow-ups and is flagged for a human");
    w2.clock.t += 5 * D;
    await tick(w2.deps, { enabled: true });
    ok(w2.transport.sent.length === 1, "no follow-up after a reply needing human handling");
    // the engine moves accounts only along the stage table: a booked meeting goes contacted -> response_classified -> qualified,
    // and a closed account is never reopened by a later reply
    const mb = await handleReply(w2.deps, "sinder", { campaign_id: c2.id, account_id: c2.accounts[0].id, text: "x", category: "meeting_booked" } as any, "x");
    const st2 = () => readAccounts(await_snap, "sinder", c2.id).find((a) => a.id === c2.accounts[0].id)!.stage;
    let await_snap = await w2.deps.store.load();
    ok(mb.category === "meeting_booked" && st2() === "qualified", "a booked meeting reaches qualified through the stage table");
    await handleReply(w2.deps, "sinder", { campaign_id: c2.id, account_id: c2.accounts[0].id, text: "unsubscribe" }, "x");
    await_snap = await w2.deps.store.load();
    ok(st2() === "closed", "an opt-out after qualifying closes the account");
    await handleReply(w2.deps, "sinder", { campaign_id: c2.id, account_id: c2.accounts[0].id, text: "x", category: "meeting_booked" } as any, "x");
    await_snap = await w2.deps.store.load();
    ok(st2() === "closed", "a closed account is not reopened by a later reply");
    // a bounce notice pasted as a reply
    const w3 = world();
    const c3 = await setup(w3.deps, "sinder", 1);
    await tick(w3.deps, { enabled: true });
    const b = await handleReply(w3.deps, "sinder", { campaign_id: c3.id, account_id: c3.accounts[0].id, subject: "Undeliverable", text: "Mail Delivery Subsystem: 550 5.1.1 recipient address rejected" }, "x");
    ok(b.category === "hard_bounce" && b.cancelled === 1, "a bounce notice received as a reply stops the follow-up");
  }

  // ---- suppression blocks ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps, "sinder", 3);
    await addSuppression(deps, "sinder", "@water2.example.com", "client request", "manual", "analyst@example.com");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 2 && !transport.sent.some((m) => m.to === accounts[2].email), "a suppressed domain is never sent to");
    ok(outboxItems(await store.load(), "sinder", id).find((x) => x.account_id === accounts[2].id && x.step === 0)!.reason.startsWith("suppressed"), "the suppressed item is cancelled with the reason");
    const w = world();
    const { campaign } = await saveCampaign(w.deps, "sinder", { plan: PLAN }, "a");
    await addSuppression(w.deps, "sinder", "x@water9.example.com", "opt_out", "test", "a");
    const [acc] = (await upsertAccounts(w.deps, "sinder", campaign.id, [{ company: "Water Co 9", email: "x@water9.example.com", contact_source: "fixture" }], "a")).accounts;
    for (const st of ["reviewed", "campaign_eligible"] as const) await moveStage(w.deps, "sinder", campaign.id, acc.id, st, "", "a");
    let threw = ""; try { await moveStage(w.deps, "sinder", campaign.id, acc.id, "contact_confirmed", "", "a"); } catch (e) { threw = String(e); }
    ok(threw.includes("suppression"), "a suppressed address cannot be confirmed as a contact");
    let ex = ""; const [exc] = (await upsertAccounts(w.deps, "sinder", campaign.id, [{ company: "Excluded Co Ltd", email: "y@ex.example.com", contact_source: "fixture" }], "a")).accounts;
    await moveStage(w.deps, "sinder", campaign.id, exc.id, "reviewed", "", "a");
    try { await moveStage(w.deps, "sinder", campaign.id, exc.id, "campaign_eligible", "", "a"); } catch (e) { ex = String(e); }
    ok(ex.includes("exclusion"), "an account matching an exclusion cannot become campaign eligible");
    let sys = ""; try { await moveStage(w.deps, "sinder", campaign.id, exc.id, "contacted", "", "a"); } catch (e) { sys = String(e); }
    ok(sys.includes("engine"), "contacted / outreach_authorized are set only by the engine");
  }

  // ---- rate limits ----
  {
    const { deps, transport, clock } = world();
    await setup(deps, "sinder", 5, { volume: { per_hour: 2, per_day: 3, max_accounts: 20 } });
    await tick(deps, { enabled: true, limit: 10 });
    ok(transport.sent.length === 2, "per-hour campaign limit respected (2 of 5)");
    clock.t += H + 1000;
    await tick(deps, { enabled: true, limit: 10 });
    ok(transport.sent.length === 3, "per-day campaign limit respected (3 in the day)");
    clock.t += D;
    await tick(deps, { enabled: true, limit: 10 });
    ok(transport.sent.length === 5, "the rest go out the next day");
  }

  // ---- transient retry ----
  {
    const { deps, transport, store, clock } = world();
    const { id, accounts } = await setup(deps, "sinder", 1);
    transport.failNext(accounts[0].email, "421", "timeout");
    const r1 = await tick(deps, { enabled: true });
    ok(r1.results[0].action === "retry", "a transient error is retried, not dropped");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0, "the retry waits for its backoff");
    clock.t += 16 * 60e3; await tick(deps, { enabled: true });
    clock.t += 31 * 60e3; await tick(deps, { enabled: true });
    const it = outboxItems(await store.load(), "sinder", id).find((x) => x.step === 0)!;
    ok(transport.sent.length === 1 && it.status === "sent" && it.attempts === 3, "sent on the third attempt after backoff");
    const w = world();
    const c = await setup(w.deps, "sinder", 1);
    w.transport.failNext(c.accounts[0].email, "421", "421", "421");
    for (let i = 0; i < 4; i++) { await tick(w.deps, { enabled: true }); w.clock.t += 2 * H; }
    ok(outboxItems(await w.store.load(), "sinder", c.id)[0].status === "failed" && w.transport.sent.length === 0, "retries are bounded (failed after 3 attempts)");
    const w2 = world();
    const c2 = await setup(w2.deps, "sinder", 1);
    w2.transport.failNext(c2.accounts[0].email, "535");
    await tick(w2.deps, { enabled: true });
    ok(readCampaign(await w2.store.load(), "sinder", c2.id)!.status === "paused", "a sender authentication error pauses the campaign");
  }

  // ---- sender verification, pilot cap, authorization rules ----
  {
    const { deps, transport, store } = world();
    const { id } = await setup(deps, "sinder", 1);
    transport.revokeSender("sinder", SENDER.email);
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0 && outboxItems(await store.load(), "sinder", id)[0].reason === "sender_not_verified", "no verified sender connection: nothing is sent");
    const w = world();
    const { campaign } = await saveCampaign(w.deps, "sinder", { plan: { ...PLAN, sender: { ...SENDER, name: "Another Person" } } }, "a");
    const [a] = (await upsertAccounts(w.deps, "sinder", campaign.id, [{ company: "Water Co", email: "q@water.example.com", contact_source: "fixture" }], "a")).accounts;
    for (const st of ["reviewed", "campaign_eligible", "contact_confirmed"] as const) await moveStage(w.deps, "sinder", campaign.id, a.id, st, "", "a");
    const sc = scopeSummary(await w.store.load(), "sinder", readCampaign(await w.store.load(), "sinder", campaign.id)!);
    const r = await authorizeCampaign(w.deps, w.transport, "sinder", campaign.id, sc.scope_hash, "admin");
    ok(!r.ok && r.errors.some((x) => x.includes("impersonation")), "authorization refuses a sender name that differs from the verified connection");
    const w2 = world();
    let err = ""; try { await setup(w2.deps, "sinder", 21); } catch (e) { err = String(e); }
    ok(err.includes("exceeds the cap of 20"), "the first authorization is limited to a reviewed pilot of up to 20 accounts");
    const w3 = world();
    const c3 = await setup(w3.deps, "sinder", 2);
    await withdrawAuthorization(w3.deps, "sinder", c3.id, "analyst@example.com");
    await tick(w3.deps, { enabled: true });
    ok(w3.transport.sent.length === 0 && readCampaign(await w3.store.load(), "sinder", c3.id)!.status === "stopped", "authorization withdrawal stops the campaign and its queue");
  }

  // ---- recent contact and account conflict across campaigns ----
  {
    const { deps, transport, store } = world();
    await setup(deps, "sinder", 1, {}, true, "same");
    await tick(deps, { enabled: true });
    const b = await setup(deps, "sinder", 1, { name: "Second" }, true, "same");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 1, "an address contacted in the last 30 days is not contacted again by another campaign");
    ok(outboxItems(await store.load(), "sinder", b.id)[0].reason.startsWith("recent_contact"), "skipped with reason recent_contact");
  }

  // ---- LinkedIn human task queue ----
  {
    const { deps, store, transport } = world();
    const li = {
      ...PLAN, channel: "linkedin", follow_up_limit: 0,
      templates: [{ id: "l0", step: 0, channel: "linkedin", kind: "connect", subject: "", body: "Hello {{first_name|there}}, {{claim:c1}}" },
        { id: "l1", step: 0, channel: "linkedin", kind: "message", subject: "", body: "Hello {{first_name|there}}, would {{offer}} be useful?" }],
    };
    const { id, accounts } = await setup(deps, "sinder", 2, li, false);
    const g = await generateLinkedInTasks(deps, "sinder", id, "analyst@example.com");
    const tasks = linkedinTasks(await store.load(), "sinder", id);
    ok(g.created === 6 && tasks.filter((t) => t.kind === "connect").every((t) => t.draft.length <= 300 && t.draft.includes(normalizePlan(PLAN).linkedin_opt_out_line) && t.draft.includes(SENDER.name)), "LinkedIn tasks carry approved drafts with identification and an opt-out line, connection notes within 300 chars");
    const again = await generateLinkedInTasks(deps, "sinder", id, "analyst@example.com");
    ok(again.created === 0, "task generation is idempotent");
    const conn = tasks.find((t) => t.kind === "connect" && t.account_id === accounts[0].id)!;
    await logLinkedInTask(deps, "sinder", { task_id: conn.id, status: "done", interaction: "connection_sent" }, "analyst@example.com");
    ok(readAccounts(await store.load(), "sinder", id).find((a) => a.id === accounts[0].id)!.stage === "contacted", "a manually logged connection request moves the account to contacted");
    const msg = tasks.find((t) => t.kind === "message" && t.account_id === accounts[0].id)!;
    const lr = await logLinkedInTask(deps, "sinder", { task_id: msg.id, status: "done", interaction: "reply_received", reply_category: "not_interested" }, "analyst@example.com");
    ok(lr.reply?.category === "not_interested" && readAccounts(await store.load(), "sinder", id).find((a) => a.id === accounts[0].id)!.stage === "closed", "a manually logged LinkedIn reply applies the same stop rules");
    ok(transport.sent.length === 0, "nothing is sent for a LinkedIn campaign");
    let threw = false; try { await enqueue(deps, "sinder", { campaign_id: id, account_id: accounts[1].id, step: 0 }, "x"); } catch { threw = true; }
    ok(threw, "a LinkedIn campaign cannot use the email outbox");
    // cross-channel: the LinkedIn contact blocks a new email campaign to the same person within 30 days
    const e = await setup(deps, "sinder", 1, { name: "Email after LinkedIn" }, true, "f");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0 && outboxItems(await store.load(), "sinder", e.id)[0].reason.startsWith("recent_contact"), "a logged LinkedIn contact counts in the cross-channel recent-contact check");
  }

  // ---- cross-workspace isolation ----
  {
    const { deps, transport, store } = world();
    const s = await setup(deps, "sinder", 2);
    const a = await setup(deps, "acme", 1, { sender: { name: "Acme Rep", email: "rep@acme-sender.example.com", org: "Acme Org", title: "", address: "" } });
    const snap = await store.load();
    ok(readCampaign(snap, "acme", s.id) === null && !listCampaigns(snap, "acme").some((c) => c.id === s.id), "another workspace cannot read the campaign");
    ok(outboxItems(snap, "acme").every((x) => x.ws === "acme") && outboxItems(snap, "acme").length === 1, "outbox lists only the workspace's own items");
    let t1 = ""; try { await handleReply(deps, "acme", { campaign_id: s.id, account_id: s.accounts[0].id, text: "unsubscribe" }, "x"); } catch (e) { t1 = String(e); }
    ok(t1.includes("not found"), "a reply cannot be recorded against another workspace's campaign");
    let t2 = ""; try { await previewMessage(deps, "acme", s.id, s.accounts[0].id); } catch (e) { t2 = String(e); }
    ok(t2.includes("not found"), "another workspace cannot preview the campaign");
    ok((await cancelCampaign(deps, "acme", s.id, "x")).ok === false, "another workspace cannot cancel the campaign");
    await emergencyStop(deps, "acme", "x");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 2 && transport.sent.every((m) => m.ws === "sinder"), "one workspace's emergency stop does not halt another's, and halts its own");
    await addSuppression(deps, "acme", s.accounts[1].email, "x", "x", "x");
    ok(!isSuppressed(await store.load(), "sinder", s.accounts[1].email, s.id), "suppression entries are per workspace");
    const sa = scopeSummary(await store.load(), "acme", readCampaign(await store.load(), "acme", a.id)!);
    ok(sa.audience.every((x) => x.email.includes("water")) && sa.audience.length === 1, "scope summaries contain only the workspace's own accounts");
  }

  console.log(fail ? `${fail} FAILED` : "all passed");
  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("FAIL (exception)", e); process.exit(1); });
