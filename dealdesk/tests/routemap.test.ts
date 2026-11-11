// Deal file -> OpportunityRoute (lib/routemap.ts), with fixture records. No network, no model, nothing is sent.
import type { DealRecord, Kind } from "@/lib/deal";
import { STATE_RANK } from "@/lib/route";
import { chooseSupplier, contactPolicy, dealParties, LEGAL_ITEMS, OWNER_APPROVED_NOTE, routeFromDeal, routeState, type DealContext } from "@/lib/routemap";
import { SCREEN_STATUSES, screenWith, type SanctionsIndex } from "@/lib/sanctions";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const NOW = "2026-11-11T09:00:00Z", DEAL = "T-FIXTURE-1";
const CTX: DealContext = { deal_id: DEAL, workspace: "sinder" };
const TENDER = { stage: "tender", deadline: "2026-12-10", buyer: "Fixture Water Board", title: "Supply of dosing pumps", link: "https://tenders.example.org/notice/1" };
let seq = 0;
const rec = (kind: Kind, record_id: string, data: Record<string, unknown>, o: Partial<DealRecord> = {}): DealRecord =>
  ({ time: `2026-11-10 10:00:${String(seq++).padStart(2, "0")}`, deal_id: DEAL, kind, record_id, version: 1, status: String(data.status || ""), data, by: "analyst@example.org", source: "panel", note: "", ...o });
const reqm = (id: string, item: string, status = "met", mandatory = true) => rec("requirement", id, { item, mandatory, status, evidence: status === "met" ? "datasheet p.2" : "" });
const quote = (o: Record<string, unknown> = {}) => rec("quote", "Q1", { supplier: "Fixture Pumps Ltd", product: "dosing pump", qty: 40, unit: "pcs", unit_price: 1200, currency: "USD", incoterm: "FOB",
  named_place: "Ningbo", valid_until: "2026-12-31", lead_time_days: 30, availability: "confirmed", source_ref: "quotation QF-77 (pdf)", ...o });
const legal = [reqm("L1", LEGAL_ITEMS.data_rights), reqm("L2", LEGAL_ITEMS.representation)];
const complete = () => [...legal, reqm("R1", "flow rate 50 l/h"), reqm("R2", "IP65 enclosure"), quote(),
  rec("economics", "econ", { role: "principal", sale_price: 60000, cost_goods: 48000, freight: 2000, insurance: null, inspection: null, funding_limit: null }),
  rec("stage", "stage", { stage: "sourcing", title: "Dosing pumps for Fixture Water Board", deadline: "2026-12-05" })];

// ---- an empty deal
{
  const v = routeState([], null, NOW, CTX), r = routeFromDeal([], null, NOW, CTX);
  ok(v.evaluation.state === "RESEARCH" || v.evaluation.state === "NEEDS_EVIDENCE", `empty deal: ${v.evaluation.state}`);
  ok(!!v.next_task && v.next_task.question.length > 10 && !!v.next_task.kind, `empty deal: a concrete next task (${v.next_task?.kind})`);
  ok(r.supply.supplier === null && r.supply.technical_fit === "unknown" && r.demand.status === "unknown" && r.demand.quantity === null && r.demand.deadline === null, "empty deal: supplier, fit, demand status, quantity and deadline stay unknown");
  const e = r.economics;
  ok(e.price_type === "none" && e.sale_price === null && e.cost === null && e.capital_need === null && e.funding_limit === null, "empty deal: every finance number is null, never zero");
  ok(r.authority.owner_mandate === "none" && r.authority.data_rights_ok === null && r.authority.representation_ok === null && r.evidence.length === 0, "empty deal: no mandate, legal checks not done, no evidence");
  ok(v.evaluation.economics.margin === null && v.evaluation.days_left === null && v.evaluation.profit_statement === "blocked", "empty deal: margin and days left are null, no profit statement");
  ok(routeState([], null, NOW, { deal_id: DEAL }).evaluation.state === "INELIGIBLE", "no workspace: the route is not evaluated for anyone");
}

// ---- a contradicted mandatory spec
{
  const recs = [...complete().filter((x) => x.record_id !== "R2"), reqm("R2", "IP65 enclosure", "not_met")];
  const v = routeState(recs, null, NOW, { ...CTX, tender: TENDER });
  ok(v.evaluation.state === "MISMATCH" && v.next_task === null && v.priority === null, `contradicted mandatory spec: ${v.evaluation.state}, no next task, no priority`);
  ok(v.evaluation.blockers.some((b) => b.code === "requirement_contradicted" && b.text.includes("IP65")), "the blocker names the requirement");
  const opt = [...complete().filter((x) => x.record_id !== "R2"), reqm("R2", "IP65 enclosure", "not_met", false)];
  ok(routeState(opt, null, NOW, { ...CTX, tender: TENDER }).evaluation.state !== "MISMATCH", "a not-met optional requirement is not a mismatch");
}

// ---- a complete quote, no owner mandate
{
  const v = routeState(complete(), null, NOW, { ...CTX, tender: TENDER }), r = routeFromDeal(complete(), null, NOW, { ...CTX, tender: TENDER });
  ok(v.evaluation.state === "READY_FOR_OWNER_REVIEW", `complete quote, no mandate: ${v.evaluation.state}`);
  ok(v.evaluation.blockers.some((b) => b.code === "no_owner_mandate") && v.next_task === null, "the limit is the missing owner mandate; approval is pending, so no next task");
  ok(r.supply.supplier === "Fixture Pumps Ltd" && r.supply.technical_fit === "supported" && v.evaluation.exact_fit, "supplier from the only quote; fit supported because every mandatory requirement is met");
  ok(r.economics.price_type === "quote" && r.economics.sale_price === 60000 && r.economics.cost === 50000 && v.evaluation.economics.margin === 10000, "economics: quote basis, cost = goods + stated freight, margin computed");
  ok(r.economics.capital_need === null && r.economics.funding_limit === null && v.evaluation.profit_statement === "blocked", "capital need and funding limit are not in the file: null, profit statement blocked");
  ok(v.evaluation.source_families === 2 && r.demand.status === "open" && r.demand.deadline === "2026-12-10" && r.time.deadline === "2026-12-05" && r.time.lead_time_days === 30, "two source families (notice, supplier quote); dates and lead time from the file");
  ok(r.supply.requirements.length === 2 && r.authority.data_rights_ok === true && r.authority.representation_ok === true, "legal checks are read from their own requirements, not counted as product requirements");
  // contact recorded, quote missing, everything else: still never past owner review without a mandate
  const variants: DealRecord[][] = [complete(), [...complete(), rec("party", "P1", { role: "supplier", name: "Fixture Pumps Ltd", status: "contacted" })],
    complete().filter((x) => x.kind !== "economics"), complete().filter((x) => x.kind !== "stage")];
  ok(variants.every((x) => STATE_RANK[routeState(x, null, NOW, { ...CTX, tender: TENDER }).evaluation.state] >= STATE_RANK.READY_FOR_OWNER_REVIEW), "without an owner mandate no variant ranks above READY_FOR_OWNER_REVIEW");
  const approved = [...complete(), rec("party", "PAPPR1", { role: "supplier", name: "Fixture Pumps Ltd", status: "contacted" }, { note: OWNER_APPROVED_NOTE })];
  const a = routeState(approved, null, NOW, { ...CTX, tender: TENDER });
  ok(a.evaluation.state === "ACTIVE" && a.evaluation.reasons.some((x) => x.includes("each outgoing message still needs approval")), "an owner-approved message on the file reads as a per-message mandate; every message still needs approval");
}

// ---- nothing is invented
{
  const noTender = routeFromDeal(complete(), null, NOW, CTX);
  ok(noTender.demand.status === "unknown" && noTender.demand.deadline === null && noTender.evidence.length === 1, "no notice in the index: demand status unknown, one source family");
  const unconfirmed = routeFromDeal([...legal, quote({ availability: "unconfirmed", unit_price: null })], null, NOW, CTX);
  ok(unconfirmed.economics.price_type === "none" && unconfirmed.evidence[0].status === "client-asserted", "a quote without a price is not a price basis; unconfirmed availability is not counterparty-confirmed");
  const flagged = routeFromDeal(complete(), { groups: [{ basis: "FOB ningbo", rows: [{ supplier: "Fixture Pumps Ltd", flags: ["no price"] } as never] }] }, NOW, CTX);
  ok(flagged.economics.price_type === "assumption", "the comparison's no-price flag removes the quote basis");
  const two = [quote(), rec("quote", "Q2", { supplier: "Other Pumps", unit_price: 1100, currency: "USD", source_ref: "email" })];
  ok(chooseSupplier(two).supplier === null && chooseSupplier(two).basis === "several candidates, none selected", "two quoting suppliers, none selected: no supplier is picked");
  const sel = [...two, rec("party", "P2", { role: "supplier", name: "other pumps", status: "selected" })];
  ok(chooseSupplier(sel).supplier === "other pumps" && routeFromDeal(sel, null, NOW, CTX).time.quote_valid_until === null, "a selected party decides; its quote has no validity date, so none is given");
  const agent = routeFromDeal([rec("economics", "econ", { role: "agent", sale_price: 0, cost_goods: null })], null, NOW, CTX);
  ok(agent.route_type === "agency" && agent.economics.sale_price === 0 && agent.economics.cost === null, "a recorded zero stays zero, a missing cost stays null");
  const old = [rec("requirement", "R1", { item: "x", mandatory: true, status: "not_met" }), rec("requirement", "R1", { item: "x", mandatory: true, status: "met", evidence: "doc" }, { version: 2 }), rec("quote", "Q9", { supplier: "Gone" }, { status: "deleted", version: 3 })];
  const o = routeFromDeal(old, null, NOW, CTX);
  ok(o.supply.requirements[0].status === "verified" && o.supply.supplier === null, "the latest version of a record wins; a deleted record is ignored");
}

// ---- send policy, display only
{
  const c = contactPolicy(Date.parse(NOW));
  ok(c.needs_owner_approval === true && c.conversation_mode === false && c.reason.startsWith("no_mandate"), "contact needs owner approval: no mandate, conversation mode off");
}
// ---- sanctions: the screen of the deal's parties sets the route's flag (three outcomes)
{
  const INDEX: SanctionsIndex = { updated: "2026-11-11 05:00", ents: [[["Blocked Pumps Trading LLC"], "OFAC SDN", "SDGT", "entity", "ref-9"]] };
  const recs = [...complete(), rec("party", "PB", { role: "buyer", name: "Fixture Water Board", status: "candidate" }), rec("party", "PD", { role: "supplier", name: "Dropped Co", status: "dropped" })];
  const parties = dealParties(recs, { ...CTX, tender: TENDER });
  ok(parties.map((p) => `${p.role}:${p.name}`).join() === "buyer:Fixture Water Board,supplier:Fixture Pumps Ltd", "the screen covers the buyer and the quoting supplier, once each; a dropped party is left out");
  ok(dealParties(complete(), { ...CTX, tender: TENDER }).some((p) => p.role === "buyer" && p.name === "Fixture Water Board"), "with no buyer party the notice's buyer is screened");
  ok(SCREEN_STATUSES.join() === "NOT_CHECKED,CHECKED_NO_ISSUE,FAILED,STALE,VERIFIED", "the status vocabulary is fixed");

  // 1. no candidate match: checked on a date, not a clearance, no alert
  const clean = screenWith(INDEX, parties, NOW), v1 = routeState(recs, null, NOW, { ...CTX, tender: TENDER, sanctions: clean });
  ok(clean.status === "CHECKED_NO_ISSUE" && clean.label.startsWith("checked, no candidate match on 2026-11-11") && /not a clearance/.test(clean.label) && clean.clearance === false && clean.candidates.length === 0,
    `no match: "${clean.label.slice(0, 44)}...", stated as not a clearance`);
  ok(routeFromDeal(recs, null, NOW, { ...CTX, tender: TENDER, sanctions: clean }).authority.sanctions_alert === false && v1.sanctions.status === "CHECKED_NO_ISSUE" && v1.sanctions.checked_on === "2026-11-11"
    && !v1.not_in_deal_file.includes("sanctions screening result") && v1.evaluation.state !== "STOPPED" && !/\bclear(ed)?\b(?! ance)/i.test(v1.sanctions.label.replace("not a clearance", "")), "no match: no alert, the card shows the check and its date and never the word clear");

  // 2. candidate match: alert, the route is STOPPED and stays so whatever else is on the file
  const bad = [...recs, rec("party", "PX", { role: "partner", name: "Blocked Pumps Trading", status: "candidate", partner_state: "candidate found" })];
  const hit = screenWith(INDEX, dealParties(bad, { ...CTX, tender: TENDER }), NOW), v2 = routeState(bad, null, NOW, { ...CTX, tender: TENDER, sanctions: hit });
  ok(hit.status === "FAILED" && hit.candidates.length === 1 && hit.candidates[0].name === "Blocked Pumps Trading" && hit.candidates[0].list === "OFAC SDN" && hit.candidates[0].ref === "ref-9" && /Qualified review required/.test(hit.label),
    "candidate match: FAILED, with the party, the list and the reference");
  ok(v2.evaluation.state === "STOPPED" && v2.evaluation.blockers.some((b) => b.code === "sanctions_alert" && /qualified review required/.test(b.text)) && v2.next_task === null && v2.priority === null && v2.sanctions.candidates.length === 1,
    "candidate match: the route's sanctions alert is set and the state is STOPPED, with no next task");
  const approved = [...bad, rec("party", "PAPPR9", { role: "supplier", name: "Fixture Pumps Ltd", status: "contacted" }, { note: OWNER_APPROVED_NOTE })];
  ok(routeState(approved, null, NOW, { ...CTX, tender: TENDER, sanctions: screenWith(INDEX, dealParties(approved, { ...CTX, tender: TENDER }), NOW) }).evaluation.state === "STOPPED", "an owner approval on file does not lift the alert");

  // 3. lists unavailable: not checked, which is neither an alert nor a pass
  const none = screenWith(null, parties, NOW), v3 = routeState(recs, null, NOW, { ...CTX, tender: TENDER, sanctions: none });
  ok(none.status === "NOT_CHECKED" && none.label.startsWith("not checked") && none.checked_on === null && none.screened.length === 0, "lists unavailable: NOT_CHECKED, no date, nobody screened");
  ok(v3.sanctions.status === "NOT_CHECKED" && routeFromDeal(recs, null, NOW, { ...CTX, tender: TENDER, sanctions: none }).authority.sanctions_alert === false && v3.evaluation.state === v1.evaluation.state, "not checked raises no alert and is shown as not checked");
  const absent = routeState(recs, null, NOW, { ...CTX, tender: TENDER });
  ok(absent.sanctions.status === "NOT_CHECKED" && absent.sanctions.label === "not checked" && absent.not_in_deal_file.includes("sanctions screening result"), "no screen passed in at all: also NOT_CHECKED, never read as clear");
  const stale = screenWith({ ...INDEX, updated: "2026-10-20 05:00" }, parties, NOW), staleHit = screenWith({ ...INDEX, updated: "2026-10-20 05:00" }, dealParties(bad, { ...CTX, tender: TENDER }), NOW);
  ok(stale.status === "STALE" && /does not count/.test(stale.label) && staleHit.status === "FAILED" && screenWith(INDEX, [], NOW).status === "NOT_CHECKED", "an out-of-date index is STALE, not a check; a candidate in it is still an alert; no names is not checked");
}
if (fail) { console.log(`${fail} failed`); process.exit(1); }
