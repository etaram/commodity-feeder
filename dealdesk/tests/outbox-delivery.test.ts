// Outbox delivery semantics (acceptance F16) with MemoryStore and TestTransport only: nothing is sent anywhere.
// Covers: delivery_unknown (never retried blindly, moved on only by reconcile or the owner), duplicate jobs and
// duplicate webhooks with one idempotency key, and an opt-out recorded between approval and dispatch.
// All names and addresses below are fixtures on example.com domains.
// Run: npx --yes esbuild@0.24.0 tests/outbox-delivery.test.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=<out>.js && node <out>.js
import { authorizeCampaign, moveStage, readAccounts, readCampaign, saveCampaign, scopeSummary, upsertAccounts } from "@/lib/outreach/campaign";
import { enqueue, handleReply, logRows, outboxItems, reconcileDelivery, startCampaign, tick, STUCK_SENDING_MS, type Deps } from "@/lib/outreach/outbox";
import { MemoryStore, nextRev } from "@/lib/outreach/store";
import { addSuppression } from "@/lib/outreach/suppression";
import { TestTransport, type Transport } from "@/lib/outreach/transport";

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
  const transport = new TestTransport([{ ws: "sinder", email: SENDER.email, name: SENDER.name }]);
  const deps: Deps = { store, transport, now: () => clock.t };
  return { store, clock, transport, deps };
}

// approve = the admin authorization of the exact audience; start = the queue is filled. Dispatch happens on tick().
async function setup(deps: Deps, n = 1, planOver: Record<string, unknown> = {}) {
  const ws = "sinder";
  const { campaign } = await saveCampaign(deps, ws, { plan: { ...PLAN, ...planOver } }, "analyst@example.com");
  const accs = Array.from({ length: n }, (_, i) => ({ company: `Water Co ${i}`, first_name: `F${i}`, email: `f${i}@water${i}.example.com`, linkedin_url: `https://www.linkedin.com/in/fixture-f${i}`, contact_source: "fixture" }));
  const { accounts } = await upsertAccounts(deps, ws, campaign.id, accs, "analyst@example.com");
  for (const a of accounts) for (const st of ["reviewed", "campaign_eligible", "contact_confirmed"] as const) await moveStage(deps, ws, campaign.id, a.id, st, "fixture review", "analyst@example.com");
  const scope = scopeSummary(await deps.store.load(), ws, (readCampaign(await deps.store.load(), ws, campaign.id))!);
  const auth = await authorizeCampaign(deps, deps.transport, ws, campaign.id, scope.scope_hash, "admin@example.com");
  if (!auth.ok) throw new Error("setup authorize failed: " + auth.errors.join("; "));
  const r = await startCampaign(deps, ws, campaign.id, "admin@example.com"); if (!r.ok) throw new Error(r.error);
  return { id: campaign.id, accounts };
}
const WS = "sinder";
const item0 = async (store: MemoryStore, id: string, accountId?: string) => outboxItems(await store.load(), WS, id).find((x) => x.step === 0 && (!accountId || x.account_id === accountId))!;
const sentLogs = async (store: MemoryStore, id: string) => logRows(await store.load(), WS, { campaign_id: id }).filter((r) => r.status === "sent");

async function main() {
  // ---- timeout after dispatch: delivery_unknown, never retried blindly ----
  {
    const { deps, transport, store, clock } = world();
    const { id, accounts } = await setup(deps);
    transport.ambiguousNext(accounts[0].email, "delivered"); // the provider accepted it, the answer never arrived
    const r1 = await tick(deps, { enabled: true });
    let it = await item0(store, id);
    ok(r1.results[0].action === "delivery_unknown" && it.status === "delivery_unknown", "a timeout after dispatch becomes delivery_unknown, not a retry");
    ok(it.reason.includes("reconcile") && it.last_error.startsWith("timeout") && it.attempts === 1, "the item keeps a reason and the provider error");
    ok(logRows(await store.load(), WS, { campaign_id: id }).some((r) => r.status === "delivery_unknown"), "a delivery_unknown event is logged");
    ok((await sentLogs(store, id)).length === 0 && readAccounts(await store.load(), WS, id)[0].stage === "outreach_authorized", "it is not recorded as sent and the account does not move to contacted");
    for (let i = 0; i < 6; i++) { clock.t += 6 * H; await tick(deps, { enabled: true }); }
    clock.t += 30 * D; const late = await tick(deps, { enabled: true });
    it = await item0(store, id);
    ok(transport.sent.length === 1 && it.status === "delivery_unknown" && late.results.length === 0, "many ticks and 31 days later: still delivery_unknown, the transport was never called again");
    ok(outboxItems(await store.load(), WS, id).length === 1, "no follow-up is queued while the first message is unresolved");
    // a duplicate job with the same key while the outcome is unknown
    const again = await enqueue(deps, WS, { campaign_id: id, account_id: accounts[0].id, step: 0 }, "duplicate-job");
    ok(!again.created && again.item.status === "delivery_unknown", "a duplicate job with the same idempotency key returns the unresolved item");
    await store.append("outbox", { time: new Date(deps.now()).toISOString(), ws: WS, campaign_id: id, id: "OB-race", rev: nextRev(deps.now()), status: "queued", data: { ...it, id: "OB-race", status: "queued" }, by: "race" });
    const r2 = await tick(deps, { enabled: true });
    ok(r2.results[0]?.action === "duplicate" && transport.sent.length === 1, "a racing duplicate row with the same key is cancelled, not sent, while the first is delivery_unknown");
    // reconcile: the provider confirms it was sent
    const rec = await reconcileDelivery(deps, WS, it.id, "admin@example.com");
    it = await item0(store, id);
    ok(rec.ok && rec.outcome === "sent" && rec.source === "provider" && it.status === "sent" && !!it.provider_id && !!it.sent_at, "reconcile: the provider confirms sent, the item becomes sent");
    ok(transport.sent.length === 1 && (await sentLogs(store, id)).length === 1, "reconcile to sent sends nothing and records exactly one sent event");
    ok(readAccounts(await store.load(), WS, id)[0].stage === "contacted" && outboxItems(await store.load(), WS, id).some((x) => x.step === 1 && x.status === "queued"), "after the confirmation the account is contacted and the follow-up is scheduled");
    const twice = await reconcileDelivery(deps, WS, it.id, "admin@example.com", "not_sent");
    ok(!twice.ok && (await item0(store, id)).status === "sent", "a sent item cannot be reconciled back into the queue");
    await tick(deps, { enabled: true });
    ok(transport.sent.filter((m) => m.step === 0).length === 1, "the first message went out exactly once overall");
  }

  // ---- reconcile: the provider confirms it was NOT sent ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps);
    transport.ambiguousNext(accounts[0].email, "lost");
    await tick(deps, { enabled: true });
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0 && (await item0(store, id)).status === "delivery_unknown", "lost in transit: delivery_unknown, no blind retry");
    const it = await item0(store, id);
    const rec = await reconcileDelivery(deps, WS, it.id, "admin@example.com");
    ok(rec.ok && rec.outcome === "requeued" && (await item0(store, id)).status === "queued", "reconcile: the provider confirms not sent, the item goes back to the queue");
    await tick(deps, { enabled: true });
    const done = await item0(store, id);
    ok(transport.sent.length === 1 && done.status === "sent" && done.attempts === 2 && transport.sent[0].idem_key === it.idem_key, "it is then sent once, with the same idempotency key");
  }

  // ---- the provider cannot say: nothing moves without the owner ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps);
    transport.ambiguousNext(accounts[0].email, "throw"); // send() itself rejects (connection reset after dispatch)
    const r = await tick(deps, { enabled: true });
    let it = await item0(store, id);
    ok(r.results[0].action === "delivery_unknown" && it.status === "delivery_unknown" && it.last_error.startsWith("network"), "a transport that throws is delivery_unknown too (it used to be retried as transient)");
    transport.lookupUnavailable = true;
    const rec = await reconcileDelivery(deps, WS, it.id, "admin@example.com");
    ok(rec.ok && rec.outcome === "unchanged" && (await item0(store, id)).status === "delivery_unknown", "an ambiguous provider answer at reconcile leaves it delivery_unknown");
    const noLookup: Transport = { name: "nolookup", live: false, verifySender: (w, e) => transport.verifySender(w, e), send: (m) => transport.send(m) };
    const rec2 = await reconcileDelivery({ ...deps, transport: noLookup }, WS, it.id, "admin@example.com");
    ok(rec2.ok && rec2.outcome === "unchanged", "a transport without a lookup cannot move it either");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 0, "still nothing was sent");
    const bad = await reconcileDelivery(deps, WS, it.id, "admin@example.com", "maybe" as never);
    ok(!bad.ok, "an owner decision must be sent or not_sent");
    const other = await reconcileDelivery(deps, "acme", it.id, "admin@other.example.com", "not_sent");
    ok(!other.ok && (await item0(store, id)).status === "delivery_unknown", "another workspace cannot reconcile the item");
    const own = await reconcileDelivery(deps, WS, it.id, "admin@example.com", "sent");
    it = await item0(store, id);
    ok(own.ok && own.outcome === "sent" && own.source === "owner" && it.status === "sent" && transport.sent.length === 0, "the owner can mark it sent after checking; nothing is sent again");
    const ev = (await sentLogs(store, id))[0];
    ok(!!ev && (ev.data as Record<string, unknown>).reconciled === "owner" && ev.by === "admin@example.com", "the sent event records who decided");
  }

  // ---- owner says not sent, but the recipient opted out in the meantime ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps);
    transport.ambiguousNext(accounts[0].email, "lost");
    await tick(deps, { enabled: true });
    const it = await item0(store, id);
    await addSuppression(deps, WS, accounts[0].email, "opt_out", "manual", "analyst@example.com");
    const rec = await reconcileDelivery(deps, WS, it.id, "admin@example.com", "not_sent");
    const r = await tick(deps, { enabled: true });
    const after = await item0(store, id);
    ok(rec.ok && rec.outcome === "requeued" && r.results[0].action === "cancelled" && after.status === "cancelled" && after.reason.startsWith("suppressed") && transport.sent.length === 0, "a requeued item passes every pre-send check again: an opt-out recorded meanwhile stops it");
  }

  // ---- a send that never returned (needs_review) follows the same rule ----
  {
    const { deps, transport, store, clock } = world();
    const { id } = await setup(deps);
    const it = await item0(store, id);
    await store.append("outbox", { time: new Date(deps.now()).toISOString(), ws: WS, campaign_id: id, id: it.id, rev: nextRev(deps.now()), status: "sending", data: { ...it, status: "sending", attempts: 1 }, by: "crashed-worker" });
    clock.t += STUCK_SENDING_MS + 1000;
    const r = await tick(deps, { enabled: true });
    ok(r.results.some((x) => x.action === "needs_review") && (await item0(store, id)).status === "needs_review" && transport.sent.length === 0, "a send that never returned becomes needs_review and is not retried");
    const rec = await reconcileDelivery(deps, WS, it.id, "admin@example.com", "not_sent");
    await tick(deps, { enabled: true });
    ok(rec.ok && transport.sent.length === 1 && (await item0(store, id)).status === "sent", "the owner can release a needs_review item; it is then sent once");
  }

  // ---- duplicate job and duplicate webhook with the same idempotency key ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps);
    const KEY = "webhook-evt-0001";
    const first = await enqueue(deps, WS, { campaign_id: id, account_id: accounts[0].id, step: 1, idem_key: KEY, due_at: new Date(deps.now()).toISOString() }, "webhook");
    const dup = await enqueue(deps, WS, { campaign_id: id, account_id: accounts[0].id, step: 1, idem_key: KEY, due_at: new Date(deps.now()).toISOString() }, "webhook");
    ok(first.created && !dup.created && dup.item.id === first.item.id, "a webhook delivered twice with one idempotency key creates one outbox item");
    await Promise.all([enqueue(deps, WS, { campaign_id: id, account_id: accounts[0].id, step: 0 }, "job-a"), enqueue(deps, WS, { campaign_id: id, account_id: accounts[0].id, step: 0 }, "job-b")]);
    ok(outboxItems(await store.load(), WS, id).filter((x) => x.step === 0).length === 1, "duplicate jobs for the same account and step keep one item");
    for (let i = 0; i < 3; i++) await tick(deps, { enabled: true });
    ok(transport.sent.filter((m) => m.step === 0).length === 1 && transport.sent.filter((m) => m.idem_key === KEY).length === 1, "each key was sent exactly once across repeated ticks");
    const after = await enqueue(deps, WS, { campaign_id: id, account_id: accounts[0].id, step: 1, idem_key: KEY }, "webhook-replay");
    await tick(deps, { enabled: true });
    ok(!after.created && after.item.status === "sent" && transport.sent.filter((m) => m.idem_key === KEY).length === 1, "a webhook replayed after the send returns the sent item and sends nothing");
    // a replayed row written straight to the store after the send (lost the race with the first worker)
    const sent = (await item0(store, id));
    await store.append("outbox", { time: new Date(deps.now()).toISOString(), ws: WS, campaign_id: id, id: "OB-replay", rev: nextRev(deps.now()), status: "queued", data: { ...sent, id: "OB-replay", status: "queued" }, by: "replay" });
    const r = await tick(deps, { enabled: true });
    ok(transport.sent.filter((m) => m.idem_key === sent.idem_key).length === 1 && r.results.every((x) => x.action !== "sent"), "a second row with an already-sent key never causes a second send");
  }

  // ---- opt-out between approval and dispatch ----
  {
    const { deps, transport, store } = world();
    const { id, accounts } = await setup(deps, 3); // authorized and queued: three approved messages wait for dispatch
    ok(outboxItems(await store.load(), WS, id).filter((x) => x.status === "queued").length === 3, "fixture: three approved messages are queued");
    await addSuppression(deps, WS, accounts[0].email, "opt_out", "unsubscribe link", "system");
    await handleReply(deps, WS, { campaign_id: id, account_id: accounts[1].id, text: "Please unsubscribe me from this list" }, "inbox");
    await tick(deps, { enabled: true });
    ok(transport.sent.length === 1 && transport.sent[0].to === accounts[2].email, "an opt-out recorded after approval and before dispatch stops the send (only the third goes out)");
    const a = await item0(store, id, accounts[0].id), b = await item0(store, id, accounts[1].id);
    ok(a.status === "cancelled" && a.reason.startsWith("suppressed") && b.status === "cancelled", "both opted-out items are cancelled with a reason");
    ok(readAccounts(await store.load(), WS, id).find((x) => x.id === accounts[0].id)!.stage === "closed", "the opted-out account is closed");
    // the opt-out lands in the same tick, after the snapshot of the first item and before the second is dispatched
    const w = world();
    const s2 = await setup(w.deps, 2);
    const real = w.transport.send.bind(w.transport);
    w.transport.send = async (m) => { const res = await real(m); if (m.to === s2.accounts[0].email) await addSuppression(w.deps, WS, s2.accounts[1].email, "opt_out", "arrived mid-tick", "system"); return res; };
    await tick(w.deps, { enabled: true });
    ok(w.transport.sent.length === 1 && !w.transport.sent.some((m) => m.to === s2.accounts[1].email), "suppression is re-read before every single send (an opt-out mid-tick stops the next item)");
  }

  process.exit(fail ? 1 : 0);
}
main().catch((e) => { console.error("FAIL (exception)", e); process.exit(1); });
