// Mission-level approval (lib/missionmandate.ts): the decision function only. Each condition has a case that passes
// and a case that does not. Nothing here sends, and the module must not be able to.
import { readFileSync } from "fs";
import { approveMission, commitmentLanguage, createMission, mayAutoSend, missionAutoSendOn, missionStatus, NEVER_PROMISE, revokeMission, validateMission,
  type MissionHistory, type MissionProposal, type OutreachMission } from "@/lib/missionmandate";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
const NOW = Date.parse("2026-11-12T10:00:00Z");

const draft = createMission({ id: "m-1", workspace: "sinder", product_spec: "316L stainless coil, 1.5 to 3 mm, 2B", purpose: "request for quotation",
  allowed_countries: ["Turkey", "India"], allowed_regions: ["East Asia"], max_recipients: 3, max_messages_per_recipient: 2, channels: ["email"],
  may_state: ["we are collecting quotations for 316L coil", "destination Mombasa", "quantity not yet known"], never_promise_extra: ["annual contract"], valid_until: "2026-11-14T22:00:00Z" });
const ap = approveMission(draft, "owner@example.com", NOW);
if (!ap.ok) throw new Error("fixture: " + ap.errors.join(", "));
const M: OutreachMission = ap.mission;

const SENT = [
  { text: "Dear Sales Team,", rests_on: "courtesy" },
  { text: "Your site lists 304 and 316L coil up to 1,500 mm wide.", rests_on: "note:1" },
  { text: "We are collecting quotations for 316L coil for delivery to Mombasa.", rests_on: "brief:we are collecting quotations for 316L coil" },
  { text: "Could you send your price per tonne, FOB, and the lead time?", rests_on: "question" }];
const P = (over: Partial<MissionProposal> = {}, sentences = SENT): MissionProposal => ({
  message: { recipient: "sales@mill.example", channel: "email", subject: "316L coil enquiry", text: sentences.map((s) => s.text).join(" ") },
  recipient_country: "Turkey", sentences, evidence: { verdict: "pass", issues: [], writer_run: "bd_opener-1", checker_run: "evidence-2" }, ...over });
const H: MissionHistory = { sent: [], last_inbound: "none" };
const withText = (extra: string, basis = "question") => P({}, [...SENT, { text: extra, rests_on: basis }]);
const why = (d: ReturnType<typeof mayAutoSend>) => (d.auto ? "" : d.reason);
const all = (d: ReturnType<typeof mayAutoSend>) => (d.auto ? "" : d.reasons.join(" | "));

// ---- flag ---------------------------------------------------------------------------------------------------
delete process.env.MISSION_AUTOSEND;
ok(missionAutoSendOn() === false, "MISSION_AUTOSEND is off by default");
const off = mayAutoSend(M, P(), H, NOW);
ok(off.auto === false && why(off) === "mission auto-send is off", "flag off: a message that meets every condition is still not automatic");
for (const v of ["0", "true", "on", "yes", " 1"]) { process.env.MISSION_AUTOSEND = v; ok(mayAutoSend(M, P(), H, NOW).auto === false && why(mayAutoSend(M, P(), H, NOW)) === "mission auto-send is off", `flag "${v}" is not "1": always false`); }
process.env.MISSION_AUTOSEND = "1";

// ---- the one positive -----------------------------------------------------------------------------------
ok(mayAutoSend(M, P(), H, NOW).auto === true, "flag on, approved mission, allowed recipient, clean check, plain request for quotation: automatic");

// ---- mission approved by the owner, not expired ---------------------------------------------------------
ok(why(mayAutoSend(draft, P(), H, NOW)).includes("not approved"), "a draft mission (never approved) is not automatic");
ok(why(mayAutoSend(null, P(), H, NOW)) === "no mission", "no mission: not automatic");
ok(why(mayAutoSend(revokeMission(M, "owner stopped it"), P(), H, NOW)).includes("not approved"), "a revoked mission is not automatic");
ok(all(mayAutoSend({ ...M, approved_by: "" }, P(), H, NOW)).includes("no recorded approval"), "status approved without an approver on record is not an approval");
ok(all(mayAutoSend({ ...M, max_recipients: 500 }, P(), H, NOW)).includes("changed after it was approved"), "widening the mission after the approval voids it");
ok(all(mayAutoSend({ ...M, allowed_countries: [...M.allowed_countries, "China"] }, P({ recipient_country: "China" }), H, NOW)).includes("changed after it was approved"), "adding a country after the approval voids it");
ok(mayAutoSend(M, P(), H, Date.parse("2026-11-14T21:59:59Z")).auto === true, "one second before valid_until: still valid");
ok(why(mayAutoSend(M, P(), H, Date.parse("2026-11-14T22:00:00Z"))) === "mission expired" && missionStatus(M, Date.parse("2026-11-15T00:00:00Z")) === "expired", "at valid_until the mission is expired");
ok(!approveMission(draft, "", NOW).ok && !approveMission(M, "owner@example.com", NOW).ok && !approveMission(draft, "owner@example.com", Date.parse("2026-12-01T00:00:00Z")).ok, "approval needs an approver, a draft, and an expiry in the future");
ok(validateMission(createMission({ id: "x", workspace: "w", product_spec: "", purpose: "", max_recipients: 0, max_messages_per_recipient: 1.5, valid_until: "soon" })).length >= 7, "a mission without product, purpose, places, caps, channels, statements or a date is not valid");
ok(NEVER_PROMISE.join("|") === "price acceptance|quantity commitment|exclusivity|signature|payment", "what may never be promised is fixed in code");

// ---- recipient: country, channel, caps ------------------------------------------------------------------
ok(mayAutoSend(M, P({ recipient_country: " india " }), H, NOW).auto === true, "a second allowed country passes (case and spaces ignored)");
ok(mayAutoSend(M, P({ recipient_country: "Japan", recipient_region: "East Asia" }), H, NOW).auto === true, "a recipient in an allowed region passes");
ok(why(mayAutoSend(M, P({ recipient_country: "China" }), H, NOW)).includes("outside the allowed countries"), "a country the mission does not list is not automatic");
ok(why(mayAutoSend(M, P({ recipient_country: "" }), H, NOW)).includes("outside the allowed countries"), "an unknown country is not automatic");
ok(why(mayAutoSend(M, { ...P(), message: { ...P().message, channel: "whatsapp" } }, H, NOW)).includes("channel"), "a channel the mission does not list is not automatic");
ok(why(mayAutoSend(M, { ...P(), message: { ...P().message, recipient: "" } }, H, NOW)) === "no recipient", "no recipient: not automatic");
const two = [{ recipient: "a@x.example" }, { recipient: "b@y.example" }], three = [...two, { recipient: "c@z.example" }];
ok(mayAutoSend(M, P(), { ...H, sent: two }, NOW).auto === true, "third recipient of three: under the recipient cap");
ok(why(mayAutoSend(M, P(), { ...H, sent: three }, NOW)).includes("recipient cap reached"), "a fourth recipient: cap reached");
ok(mayAutoSend(M, P(), { ...H, sent: [...three.slice(0, 2), { recipient: "Sales@Mill.example" }] }, NOW).auto === true, "a second message to a recipient already counted does not need a free slot");
ok(why(mayAutoSend(M, P(), { ...H, sent: [{ recipient: "sales@mill.example" }, { recipient: "mailto:SALES@mill.example" }] }, NOW)).includes("message cap for this recipient"), "a third message to the same recipient: per-recipient cap reached");
ok(all(mayAutoSend(M, P(), undefined as unknown as MissionHistory, NOW)).includes("history is missing"), "without a history the caps cannot be checked: not automatic");

// ---- evidence verdict -----------------------------------------------------------------------------------
const ev = (e: Partial<MissionProposal["evidence"]>) => P({ evidence: { verdict: "pass", issues: [], writer_run: "w", checker_run: "c", ...e } });
ok(mayAutoSend(M, ev({}), H, NOW).auto === true, "verdict pass with zero issues by another run passes");
ok(why(mayAutoSend(M, ev({ verdict: "send_back" }), H, NOW)).includes("not pass") && why(mayAutoSend(M, ev({ verdict: "block" }), H, NOW)).includes("not pass"), "send_back and block are not automatic");
ok(why(mayAutoSend(M, ev({ issues: ["fact 2 is older than a year"] }), H, NOW)).includes("open issues"), "a pass with an issue is not automatic");
ok(why(mayAutoSend(M, ev({ checker_run: "w" }), H, NOW)).includes("separate run") && why(mayAutoSend(M, ev({ writer_run: "" }), H, NOW)).includes("separate run"), "a check by the writer's own run, or with no run on record, is not automatic");
ok(why(mayAutoSend(M, { ...P(), evidence: undefined as unknown as MissionProposal["evidence"] }, H, NOW)).includes("missing"), "no evidence check at all: not automatic");

// ---- commitment language --------------------------------------------------------------------------------
const CAUGHT: [string, string][] = [
  ["We accept your offer.", "accept"], ["Your price is acceptable to us.", "accept"], ["We agree to these terms.", "agree"], ["Agreed, thank you.", "agree"],
  ["We confirm the order for next month.", "confirm_order"], ["Please consider this a firm order.", "confirm_order"], ["We would like to place an order.", "confirm_order"],
  ["We will pay 30 percent upfront.", "pay"], ["We'll wire the amount on Monday.", "pay"], ["A deposit can be arranged this week.", "pay"], ["We can open a letter of credit.", "pay"],
  ["We would make you our exclusive supplier.", "exclusive"], ["You would be our sole supplier in Kenya.", "exclusive"], ["We are ready to sign this week.", "sign"], ["The contract awaits our signature.", "sign"],
  ["We guarantee repeat orders.", "guarantee"], ["We commit to 500 tonnes a quarter.", "commit"], ["You have a deal.", "commit"], ["We promise a long relationship.", "commit"],
  ["We will buy 500 tonnes.", "quantity"], ["We'll take 200 tonnes at that level.", "price_acceptance"],
  ["USD 640 per tonne works for us.", "price_acceptance"], ["OK at 640 per tonne.", "price_acceptance"], ["640 is fine.", "price_acceptance"], ["Let's go with 1,200 per tonne.", "price_acceptance"], ["Please go ahead with 20 tonnes.", "price_acceptance"]];
for (const [t, kind] of CAUGHT) {
  const d = mayAutoSend(M, withText(t, "courtesy"), H, NOW);
  ok(commitmentLanguage(t).includes(kind) && !d.auto && all(d).includes("commitment language"), `commitment caught (${kind}): ${t}`);
}
ok(commitmentLanguage(SENT.map((s) => s.text).join(" ")).length === 0, "a plain request for quotation holds no commitment wording");
ok(commitmentLanguage("What is your minimum order quantity and lead time for 316L coil 2 mm?").length === 0 && commitmentLanguage("Good morning, we are looking for 316L coil, 20 to 40 tonnes, quantity not yet final.").length === 0, "asking about quantity or naming an open range is not a commitment");
ok(all(mayAutoSend(M, { ...P(), message: { ...P().message, subject: "We accept" } }, H, NOW)).includes("commitment language"), "commitment wording in the subject is caught too");
ok(all(mayAutoSend(M, withText("Could this become an annual contract?"), H, NOW)).includes("the mission forbids promising: annual contract"), "a phrase the owner added to never-promise is caught");
ok(all(mayAutoSend(M, withText("נשמח לקבל הצעת מחיר?"), H, NOW)).includes("not in Latin script"), "a text the detector cannot read is not automatic");
const f = (facts: MissionProposal["message"]["facts"]) => ({ ...P(), message: { ...P().message, facts } });
ok(mayAutoSend(M, f({ notes: ["nothing special"], topics: ["quotation"] }), H, NOW).auto === true, "harmless extracted facts do not stop an automatic message");
ok(all(mayAutoSend(M, f({ commitments: [{ kind: "pay" }] }), H, NOW)).includes("reported a commitment") && all(mayAutoSend(M, f({ counterparty_requests: ["exclusivity"] }), H, NOW)).includes("asked for a commitment"), "a commitment reported by the draft step, or asked by the counterparty, is not automatic");
ok(!mayAutoSend(M, f({ prices: [{ amount: 640, currency: "USD", unit: "tonne" }] }), H, NOW).auto && !mayAutoSend(M, f({ flags: { legal: true } }), H, NOW).auto && !mayAutoSend(M, f({ actions: ["sign"] }), H, NOW).auto && !mayAutoSend(M, f({ new_parties: ["Another Co"] }), H, NOW).auto, "a stated price, a legal flag, an action or a new party is not automatic");
ok(!mayAutoSend(M, { ...P(), message: { ...P().message, attachments: ["spec.pdf"] } }, H, NOW).auto, "an attachment is not covered by a mission");

// ---- what may be stated ---------------------------------------------------------------------------------
ok(mayAutoSend(M, withText("The destination is Mombasa.", "brief:Destination Mombasa"), H, NOW).auto === true, "a statement that rests on a may_state line passes");
ok(why(mayAutoSend(M, withText("We are the largest importer in East Africa.", "brief:largest importer in East Africa"), H, NOW)).includes("outside what may be stated"), "a statement resting on a line the mission does not list is not automatic");
ok(why(mayAutoSend(M, withText("We are the largest importer in East Africa.", ""), H, NOW)).includes("outside what may be stated"), "a statement with no basis is not automatic");
ok(why(mayAutoSend(M, withText("We supply 14 government projects across the whole of East Africa every single year.", "courtesy"), H, NOW)).includes("outside what may be stated"), "a claim labelled courtesy does not pass as a courtesy");
ok(why(mayAutoSend(M, withText("We need this urgently.", "question"), H, NOW)).includes("outside what may be stated"), "a statement labelled question is not a question");
const uncovered = P(); uncovered.message.text += " We also represent a ministry.";
ok(why(mayAutoSend(M, uncovered, H, NOW)).includes("do not cover the whole text"), "text that is not in the checked sentences is not automatic");
ok(all(mayAutoSend(M, f({ claims_used: ["we hold ISO 9001"] }), H, NOW)).includes("a claim the mission does not list") && mayAutoSend(M, f({ claims_used: ["destination mombasa"] }), H, NOW).auto === true, "claims used must be among the mission's statements");

// ---- what the message answers ---------------------------------------------------------------------------
ok(mayAutoSend(M, P(), { sent: [{ recipient: "sales@mill.example" }], last_inbound: "expected" }, NOW).auto === true, "an answer to the expected response (the quotation asked for) may be automatic");
ok(why(mayAutoSend(M, P(), { ...H, last_inbound: "unexpected" }, NOW)) === "reply to an unexpected response", "an answer to an unexpected response goes to the owner");
ok(why(mayAutoSend(M, P(), { ...H, last_inbound: "negative" }, NOW)) === "reply to a negative response", "an answer to a negative response goes to the owner");
ok(why(mayAutoSend(M, P(), { sent: [] } as unknown as MissionHistory, NOW)).includes("not known"), "when nobody classified the inbound message, it goes to the owner");
ok(why(mayAutoSend(M, P(), { ...H, opt_out: true }, NOW)).includes("not to be contacted") && !mayAutoSend(M, f({ opt_out_detected: true }), H, NOW).auto, "an opt-out is never automatic");

// ---- every reason is reported, and the module cannot send -----------------------------------------------
const many = mayAutoSend(M, { ...P({ recipient_country: "China", evidence: { verdict: "block", issues: ["x"], writer_run: "w", checker_run: "w" } }) }, { sent: three, last_inbound: "negative" }, NOW);
ok(!many.auto && many.reasons.length >= 5 && many.reason === many.reasons[0], "all failing conditions are listed for the owner, the first one as the reason");
const src = readFileSync("lib/missionmandate.ts", "utf8");
const imports = [...src.matchAll(/^import .* from "([^"]+)";$/gm)].map((x) => x[1]);
ok(imports.join(",") === "crypto,@/lib/mandate", "the module imports only crypto and lib/mandate.ts: no mailer, no send guard, no sheet, no network");
const users = ["lib/sendguard.ts", "lib/mailer.ts", "lib/dealagent.ts", "lib/pipeline.ts", "lib/outbox.ts"].filter((p) => { try { return readFileSync(p, "utf8").includes("missionmandate"); } catch { return false; } });
ok(users.length === 0, "no sending code refers to the mission mandate");

process.exit(fail ? 1 : 0);
