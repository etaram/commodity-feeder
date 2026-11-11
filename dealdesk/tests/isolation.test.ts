// F17 tenant isolation, adversarial: workspace "acme" holds confidential records; a signed-in analyst (and an admin)
// of workspace "beta" tries every read route with guessed ids, the lists, the search over research memory, the
// caches and the text assembled for the model; the original workspace ("sinder") must not find acme's material in
// its shared panel keys either. The real route handlers run with the real gate() over an in-memory sheet and a
// recording model stand-in (tests/build-agent-test.mjs, "isolation" mode). No network: fetch answers 404.
import { NextRequest } from "next/server";
import { signSession } from "@/lib/auth";
import { JAR } from "./mocks/next-headers";
import { TABS, OWNER_CONTACT } from "./mocks/sheets-isolation";
import { AI } from "./mocks/anthropic";
import { GET as dealGET, POST as dealPOST } from "@/app/api/deal/route";
import { GET as routeStateGET } from "@/app/api/deal/route-state/route";
import { GET as missionsGET, POST as missionsPOST } from "@/app/api/missions/route";
import { GET as clientsGET, POST as clientsPOST } from "@/app/api/clients/route";
import { GET as clientGET, PUT as clientPUT } from "@/app/api/clients/[id]/route";
import { GET as prospectsGET } from "@/app/api/clients/[id]/prospects/route";
import { POST as targetsPOST } from "@/app/api/clients/[id]/targets/route";
import { GET as campaignGET, POST as campaignPOST } from "@/app/api/outreach/campaign/route";
import { GET as accountsGET, POST as accountsPOST } from "@/app/api/outreach/accounts/route";
import { GET as outboxGET } from "@/app/api/outreach/outbox/route";
import { GET as outLogGET } from "@/app/api/outreach/log/route";
import { GET as linkedinGET } from "@/app/api/outreach/linkedin/route";
import { GET as suppressionGET, POST as suppressionPOST } from "@/app/api/outreach/suppression/route";
import { POST as previewPOST } from "@/app/api/outreach/preview/route";
import { GET as assertionsGET, POST as assertionsPOST } from "@/app/api/panel/assertions/route";
import { POST as contactPOST } from "@/app/api/panel/contact/route";
import { POST as panelGetPOST } from "@/app/api/panel/get/route";
import { POST as appendPOST } from "@/app/api/panel/append/route";
import { POST as runPOST } from "@/app/api/panel/run/route";
import { POST as reversePOST } from "@/app/api/panel/reverse/route";
import { POST as costsPOST } from "@/app/api/panel/costs/route";
import { POST as aiPOST } from "@/app/api/panel/ai/route";
import { POST as knowPOST } from "@/app/api/panel/know/route";
import { GET as adminGET, POST as adminPOST } from "@/app/api/panel/admin/route";
import { POST as jobPOST } from "@/app/api/job/route";
import { POST as decisionPOST } from "@/app/api/decision/route";
import { GET as activityGET } from "@/app/api/activity/route";
import { GET as mcpKeyGET } from "@/app/api/mcp/key/route";
import { GET as usersGET } from "@/app/api/users/route";
import { remember, backfillJobs } from "@/lib/researchmemory";
import { readAssertions } from "@/lib/assertionstore";
import { readOnlyTool } from "@/lib/dealagent";
import { workspaceOf } from "@/lib/users";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.AUTH_SECRET = "test-secret";
process.env.ANTHROPIC_API_KEY = "test-not-a-key";
globalThis.fetch = (async () => new Response("", { status: 404 })) as typeof fetch;

type J = Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
type Role = "viewer" | "analyst" | "admin";
const seenBy: Record<string, string[]> = {};   // every response body, per signed-in workspace
let who = "";
const as = (email: string, role: Role, ws: string) => { JAR.dd_session = signSession(email, role, email, 1, ws); who = ws; AI.who = ws; };
const req = (path: string, method = "GET", body?: unknown) => new NextRequest("http://localhost" + path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { "content-type": "application/json" } }) });
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });
const read = async (r: Response | Promise<Response>) => { const x = await r; const text = await x.text(); (seenBy[who] ||= []).push(text); let j: J = {}; try { j = JSON.parse(text); } catch { j = {}; } return { status: x.status, j, text }; };

const ACME = () => as("ana@acme.test", "analyst", "acme"), ACME_ADMIN = () => as("boss@acme.test", "admin", "acme");
const BETA = () => as("eve@beta.test", "analyst", "beta"), BETA_ADMIN = () => as("root@beta.test", "admin", "beta");
const SINDER = () => as("op@sinder.test", "admin", "sinder");

// Strings that exist only in acme's records. None of them may ever reach beta or the original workspace's shared keys.
const M = {
  sheet: "ZQX-MEMBRANE-DATASHEET-MX9", price: "4321.77", supplier: "Zeolite Hidden Supplier GmbH", deal: "T-ACME-SECRET-1", mission: "ZQX-MISSION-GOAL",
  memory: "zqx-contact@hidden-supplier.example", campaign: "ZQX-CAMPAIGN-PILOT", account: "zqx-buyer@prospect.example", research: "ZQX-RESEARCH-TARGET", costs: "ZQX-COSTED-CARGO", ai: "ZQX-AI-PROMPT", reverse: "ZQX-REVERSE-DOC",
};
// the deal id is what the attacker guesses and sends, so a route may echo it back: it is not counted as a leaked record
const MARKS = Object.values(M).filter((m) => m !== M.deal);
const leaks = (text: string) => MARKS.filter((m) => text.includes(m));
const usersRow = (email: string, role: Role, ws: string) => [email, email, role, "active", "", "password", "", "", "", "", "", "", ws];

(async () => {
  TABS["Users"] = [usersRow("ana@acme.test", "analyst", "acme"), usersRow("boss@acme.test", "admin", "acme"), usersRow("eve@beta.test", "analyst", "beta"), usersRow("root@beta.test", "admin", "beta"), usersRow("op@sinder.test", "admin", "")];

  // ------------------------------------------------------------------ fixture: acme's confidential records
  ACME();
  const made = await read(clientsPOST(req("/api/clients", "POST", { legal_name: "Acme Membranes Ltd", country: "ISR", business_objective: `Sell ${M.sheet}`,
    claims: [{ field: "products_services", value: `${M.sheet}: salt rejection 99.83 percent, list price ${M.price} USD`, source_ref: "datasheet page 1" }], private_notes: [`floor price ${M.price}`] })));
  const clientId = String(made.j.client_id || "");
  ok(made.status === 201 && /^CL-/.test(clientId), "fixture: acme creates a client with a confidential datasheet claim");
  ok((await read(dealPOST(req("/api/deal", "POST", { deal_id: M.deal, kind: "stage", data: { stage: "sourcing", title: `Supply of ${M.sheet}`, country: "KEN", value_usd: 900000 } })))).j.ok === true, "fixture: acme opens a deal");
  ok((await read(dealPOST(req("/api/deal", "POST", { deal_id: M.deal, kind: "quote", data: { supplier: M.supplier, country: "DEU", product: M.sheet, qty: 40, unit: "pcs", unit_price: Number(M.price), currency: "USD", incoterm: "FOB", named_place: "Hamburg", source_ref: "e-mail of 3 Nov" } })))).j.ok === true, "fixture: acme records a supplier quote with its price");
  const mission = await read(missionsPOST(req("/api/missions", "POST", { type: "deal_execution", goal: M.mission, deal_id: M.deal, cost_budget_usd: 50 })));
  const missionType = mission.j.ok ? "deal_execution" : String((mission.j.error || "").split(": ")[1] || "").split(", ")[0];
  const mission2 = mission.j.ok ? mission : await read(missionsPOST(req("/api/missions", "POST", { type: missionType, goal: M.mission, deal_id: M.deal, cost_budget_usd: 50 })));
  ok(mission2.j.ok === true && /\S/.test(String(mission2.j.mission?.id || "")), "fixture: acme records a mission");
  const kept = await remember({ ws: "acme", by: "ana@acme.test", job: "company_research", subject: { kind: "supplier", name: "Hidden Supplier", country: "DEU" }, text: `Hidden Supplier makes ${M.sheet} elements for brackish water plants and sells through agents.\nContact: ${M.memory}\nNext step: ask for the ${M.price} tier`, sources: [{ url: "https://hidden-supplier.example/" }] });
  ok(kept > 0, "fixture: acme's research memory holds facts");
  const asr = await read(assertionsPOST(req("/api/panel/assertions", "POST", { entity: "Hidden Supplier", country: "DEU", property: "unit_price", value: `${M.price} USD per element`, status: "observed", evidence: { excerpt: `quoted ${M.price}` } })));
  ok(asr.j.ok === true, "fixture: acme adds a price fact to the ledger");
  const camp = await read(campaignPOST(req("/api/outreach/campaign", "POST", { plan: { name: M.campaign, client: "Acme Membranes Ltd", segment: "EPC", offer: `${M.sheet} at ${M.price}` } })));
  const campId = String(camp.j.campaign?.id || "");
  ok(/^CMP-/.test(campId), "fixture: acme saves an outreach campaign");
  const accs = await read(accountsPOST(req("/api/outreach/accounts", "POST", { campaign_id: campId, accounts: [{ company: "Prospect Water Co", contact_name: "Pat Lee", email: M.account, contact_source: "trade fair list", country: "KEN" }] })));
  const acmeAccounts = (await read(accountsGET(req(`/api/outreach/accounts?campaign_id=${campId}`)))).j.accounts || [];
  ok(accs.j.ok === true && acmeAccounts.length === 1, "fixture: the campaign has one account");
  const accId = String(acmeAccounts[0]?.id || "");
  ok((await read(suppressionPOST(req("/api/outreach/suppression", "POST", { value: M.account, reason: "asked not to be contacted" })))).j.ok === true, "fixture: acme has a suppression entry");
  // acme's own AI-assisted work (this is what fills the caches and, before the fix, the shared 'Panel Jobs' tab)
  AI.reply = () => `Findings about ${M.research}.\n\nNext step: call them.`;
  ok((await read(runPOST(req("/api/panel/run", "POST", { type: "company_research", target: M.research, context: { supplier: M.research, country: "DEU" }, request: `price floor ${M.price}` })))).j.ok === true, "fixture: acme runs a research job");
  AI.reply = (p) => (/Return JSON ONLY/.test(p) ? JSON.stringify({ doc_type: "PO", product: "", buyer_hints: [M.reverse], search_terms: [] }) : `## Reconstruction of ${M.reverse}`);
  ok((await read(reversePOST(req("/api/panel/reverse", "POST", { text: `Purchase order for ${M.reverse}`, lang: "en" })))).j.ok === true, "fixture: acme reconstructs a deal document");
  AI.reply = () => JSON.stringify({ duty_pct: 7.5, duty_basis: `HS 8421 for ${M.costs}`, freight_pct: 6, freight_basis: "DEU sea", other_pct: 4, other_basis: "bonds", origin: "DEU", incoterm: "DDP" });
  const costA = await read(costsPOST(req("/api/panel/costs", "POST", { id: M.deal, title: M.costs, country: "KEN", value_usd: 900000 })));
  ok(costA.j.ok === true && costA.j.duty_basis.includes(M.costs), "fixture: acme costs its own (manual) deal");
  AI.reply = () => `Summary that repeats ${M.ai}`;
  const SHARED_PROMPT = "Summarise the open questions on our current deal.";
  ok((await read(aiPOST(req("/api/panel/ai", "POST", { prompt: SHARED_PROMPT })))).j.text.includes(M.ai), "fixture: acme gets a quick AI answer");
  AI.reply = () => "A neutral answer.\n\nNext step: none.";

  // ------------------------------------------------------------------ beta: guessed ids on every read route
  BETA();
  const before = JSON.stringify(TABS);
  const d = await read(dealGET(req(`/api/deal?id=${M.deal}`)));
  ok(d.status === 200 && d.j.records.length === 0 && d.j.versions === 0, "deal: another workspace's deal id reads as an empty deal");
  const ghost = await read(dealGET(req("/api/deal?id=T-NO-SUCH-DEAL")));
  ok(JSON.stringify({ ...d.j, routes: 0, routes_he: 0, readiness: 0 }) === JSON.stringify({ ...ghost.j, routes: 0, routes_he: 0, readiness: 0 }), "deal: a real foreign id and an id that does not exist are indistinguishable");
  ok((await read(dealGET(req("/api/deal?pipeline=1")))).j.deals.length === 0, "deal pipeline: lists nothing of another workspace");
  const rs = await read(routeStateGET(req(`/api/deal/route-state?id=${M.deal}`)));
  ok(rs.j.records === 0 && !leaks(rs.text).length, "deal route state: no records of another workspace");
  ok((await read(missionsGET(req("/api/missions")))).j.missions.length === 0 && (await read(missionsGET(req(`/api/missions?deal_id=${M.deal}`)))).j.missions.length === 0, "missions: list and deal filter return nothing of another workspace");
  ok((await read(clientsGET())).j.clients.length === 0, "clients: the list is empty for another workspace");
  ok((await read(clientGET(req(`/api/clients/${clientId}`), ctx(clientId)))).status === 404 && (await read(clientPUT(req(`/api/clients/${clientId}`, "PUT", { name: "taken" }), ctx(clientId)))).status === 404
    && (await read(prospectsGET(req(`/api/clients/${clientId}/prospects`), ctx(clientId)))).status === 404 && (await read(targetsPOST(req(`/api/clients/${clientId}/targets`, "POST", { action: "profiles" }), ctx(clientId)))).status === 404,
    "clients: a foreign client id answers 404 on read, edit, prospects and targets");
  ok((await read(campaignGET(req("/api/outreach/campaign")))).j.campaigns.length === 0, "outreach: the campaign list is empty for another workspace");
  ok((await read(campaignGET(req(`/api/outreach/campaign?id=${campId}`)))).status === 404, "outreach: a foreign campaign id answers 404");
  const ba = await read(accountsGET(req(`/api/outreach/accounts?campaign_id=${campId}`)));
  ok((ba.j.accounts || []).length === 0 && (await read(accountsGET(req(`/api/outreach/accounts?campaign_id=${campId}&account_id=${accId}`)))).status === 404, "outreach: a foreign campaign's accounts and a guessed account id return nothing");
  ok((await read(outboxGET(req(`/api/outreach/outbox?campaign_id=${campId}`)))).j.items.length === 0 && (await read(outLogGET(req(`/api/outreach/log?campaign_id=${campId}`)))).j.events.length === 0
    && (await read(linkedinGET(req(`/api/outreach/linkedin?campaign_id=${campId}`)))).j.tasks.length === 0 && (await read(suppressionGET())).j.entries.length === 0, "outreach: outbox, log, LinkedIn tasks and suppression list are empty for another workspace");
  const pv = await read(previewPOST(req("/api/outreach/preview", "POST", { campaign_id: campId, account_id: accId })));
  ok(pv.status === 404 && !leaks(pv.text).length, "outreach: previewing a foreign campaign's message answers 404");
  // search over the research memory and the ledger
  const all = await read(assertionsGET(req("/api/panel/assertions")));
  ok(all.j.total === 0, "ledger: listing everything returns no row of another workspace");
  const byName = await read(assertionsGET(req("/api/panel/assertions?entity=Hidden%20Supplier&country=DEU")));
  ok(byName.j.total === 0 && (await read(assertionsGET(req("/api/panel/assertions?property=unit_price")))).j.total === 0, "ledger: searching by the entity or the property finds nothing of another workspace");
  const quarantine = await read(assertionsPOST(req("/api/panel/assertions", "POST", { quarantine: String(asr.j.row?.id || ""), status: "rejected", reason: "probing" })));
  ok(quarantine.status === 403 || quarantine.status === 404, "ledger: another workspace cannot quarantine (or confirm) a foreign fact id");
  const ct = await read(contactPOST(req("/api/panel/contact", "POST", { name: "Hidden Supplier", country: "DEU" })));
  ok(ct.j.contact === null && !leaks(ct.text).length, "contact card: acme's researched contact is not shown to beta");
  const oc = await read(contactPOST(req("/api/panel/contact", "POST", { name: "Grain SA", country: "ZAF" })));
  ok(oc.j.contact === null && !oc.text.includes(OWNER_CONTACT.email), "contact card: the original workspace's stored contact is not shown to beta");
  ok(JSON.stringify((await read(knowPOST(req("/api/panel/know", "POST", { names: ["Grain SA"] })))).j.matches) === "{}", "network: the original workspace's contacts are not searched for beta");
  // exports of the private panel tabs
  for (const key of ["jobs", "pursuits", "contacts", "accounts", "intel", "bd", "projects", "ptasks", "approvals", "decisions", "Deal Records", "Client Dossiers", "Missions", "Assertions"]) {
    const g = await read(panelGetPOST(req("/api/panel/get", "POST", { key })));
    ok(g.j.scoped === true && JSON.stringify(g.j.values) === "[[]]", `panel export "${key}": an empty grid for another workspace`);
  }
  // writes into the original workspace's private tabs
  ok((await read(appendPOST(req("/api/panel/append", "POST", { range: "'Pursuits'!A1", values: [["x"]] })))).status === 403, "pursuits: another workspace cannot write the original workspace's tab");
  ok((await read(jobPOST(req("/api/job", "POST", { type: "quote", target: "beta target" })))).status === 403 && (await read(decisionPOST(req("/api/decision", "POST", { id: "T-1", decision: "Go" })))).status === 403,
    "research queue and decisions: another workspace cannot write the original workspace's tabs");
  ok(JSON.stringify(TABS) === before, "none of beta's probes changed a stored row");

  // ------------------------------------------------------------------ beta: cached summaries
  const nCalls = AI.calls.length;
  AI.reply = () => JSON.stringify({ duty_pct: 1, duty_basis: "beta basis", freight_pct: 1, freight_basis: "x", other_pct: 1, other_basis: "x", origin: "CHN", incoterm: "CIF" });
  const costB = await read(costsPOST(req("/api/panel/costs", "POST", { id: M.deal, title: "something else", country: "KEN" })));
  ok(costB.j.ok === true && !costB.j.cached && costB.j.duty_basis === "beta basis", "cost cache: a guessed deal id does not return another workspace's cached answer");
  AI.reply = () => "beta's own answer";
  const aiB = await read(aiPOST(req("/api/panel/ai", "POST", { prompt: SHARED_PROMPT })));
  ok(aiB.j.text === "beta's own answer" && !aiB.j.cached && AI.calls.length === nCalls + 2, "quick AI cache: the same prompt from another workspace is answered afresh, not from the cache");
  ok((await read(aiPOST(req("/api/panel/ai", "POST", { prompt: SHARED_PROMPT })))).j.cached === true, "quick AI cache: still serves the workspace that asked");
  ACME();
  ok((await read(costsPOST(req("/api/panel/costs", "POST", { id: M.deal, title: M.costs, country: "KEN" })))).j.cached === true, "cost cache: still serves the workspace that asked");

  // ------------------------------------------------------------------ beta: text assembled for the model
  BETA();
  AI.reply = () => "A neutral answer.\n\nNext step: none.";
  await read(runPOST(req("/api/panel/run", "POST", { type: "company_research", target: "Hidden Supplier (DEU)", context: { supplier: "Hidden Supplier", country: "DEU" }, request: "what do we know already" })));
  await read(runPOST(req("/api/panel/run", "POST", { type: "deal_research", target: "deal", target_id: M.deal, request: "summarise the quotes on this deal" })));
  const bc = await read(clientsPOST(req("/api/clients", "POST", { legal_name: "Beta Pumps Ltd", claims: [{ field: "products_services", value: "Pumps", source_ref: "page 1" }] })));
  BETA_ADMIN();
  await read(clientPUT(req(`/api/clients/${bc.j.client_id}`, "PUT", { status: "reviewed" }), ctx(String(bc.j.client_id))));
  await read(targetsPOST(req(`/api/clients/${bc.j.client_id}/targets`, "POST", { action: "profiles" }), ctx(String(bc.j.client_id))));
  const betaPrompts = AI.calls.filter((c) => c.who === "beta");
  ok(betaPrompts.length >= 4 && betaPrompts.every((c) => !leaks(c.prompt).length), `model context: none of the ${betaPrompts.length} prompts built for beta contains a record of acme`);
  ok(JSON.parse(await readOnlyTool("supplier_contact", { company: "Grain SA" }, "beta")).email === undefined, "deal agent: the stored supplier contact is not given to a run of another workspace");
  ok(JSON.parse(await readOnlyTool("supplier_contact", { company: "Grain SA" }, "sinder")).email === OWNER_CONTACT.email, "deal agent: the original workspace still gets its stored contact");
  ok((await workspaceOf("eve@beta.test")) === "beta" && (await workspaceOf("op@sinder.test")) === "sinder" && (await workspaceOf("nobody@x.test")) === "sinder", "a project or agent run takes its workspace from the account, not a default");

  // ------------------------------------------------------------------ beta's admin: shared tabs and keys
  const act = await read(activityGET(req("/api/activity?limit=2000")));
  ok(act.j.rows.length > 0 && act.j.rows.every((r: J) => /@beta\.test$/.test(r.email)) && !leaks(act.text).length, "activity log: another workspace's admin sees its own accounts only");
  const sum = await read(activityGET(req("/api/activity?summary=1")));
  ok(sum.j.users.every((u: J) => /@beta\.test$/.test(u.email)), "activity summary: its own accounts only");
  const users = await read(usersGET());
  ok(users.j.users.length === 2 && users.j.users.every((u: J) => u.workspace === "beta"), "accounts: another workspace's admin lists its own accounts only");
  ok((await read(mcpKeyGET(new Request("http://localhost/api/mcp/key")))).status === 403, "MCP address: not given to another workspace's admin");
  ok((await read(adminPOST(new Request("http://localhost/api/panel/admin", { method: "POST", body: JSON.stringify({ action: "backfill_research" }) })))).status === 403, "research backfill: not run by another workspace's admin");
  TABS["App Log"] = [["2026-11-11 10:00", "error", "run", `job failed for ${M.research}`, "ana@acme.test", "", "", ""]];
  const betaFacts = (await readAssertions(true)).filter((a) => a.ws === "beta").length;
  const adm = await read(adminGET());
  ok(adm.status === 200 && adm.j.warnings.length === 0 && adm.j.assertions.total === betaFacts && !adm.j.assertions.by_property.unit_price && !leaks(adm.text).length, "admin panel: no log line and no ledger count of another workspace");

  // ------------------------------------------------------------------ everything beta ever received
  const got = (seenBy.beta || []).join("\n");
  ok(!leaks(got).length, `nothing acme owns appears in any of the ${(seenBy.beta || []).length} responses beta received` + (leaks(got).length ? `: ${leaks(got).join(", ")}` : ""));

  // ------------------------------------------------------------------ the original workspace's operator
  SINDER();
  let shared = "";
  for (const key of ["jobs", "pursuits", "contacts", "accounts", "intel", "bd", "projects", "ptasks", "approvals", "websup"]) shared += (await read(panelGetPOST(req("/api/panel/get", "POST", { key, fresh: true })))).text;
  ok(!leaks(shared).length, "original workspace: no client or other-workspace record in the shared panel keys" + (leaks(shared).length ? `: ${leaks(shared).join(", ")}` : ""));
  ok(!leaks(JSON.stringify([TABS["Panel Jobs"] || [], TABS["Web Suppliers"] || [], TABS["Decisions"] || [], TABS["Pursuits"] || []])).length, "another workspace's research is not stored in the original workspace's tabs");
  ok((await read(dealGET(req(`/api/deal?id=${M.deal}`)))).j.records.length === 0 && (await read(dealGET(req("/api/deal?pipeline=1")))).j.deals.length === 0, "original workspace: acme's deal is not in its deal routes");
  ok((await read(clientsGET())).j.clients.length === 0 && (await read(clientGET(req(`/api/clients/${clientId}`), ctx(clientId)))).status === 404, "original workspace: acme's client is reachable only inside acme");
  ok((await read(assertionsGET(req("/api/panel/assertions")))).j.total === 0 && (await read(missionsGET(req("/api/missions")))).j.missions.length === 0 && (await read(campaignGET(req("/api/outreach/campaign")))).j.campaigns.length === 0, "original workspace: no ledger row, mission or campaign of another workspace");
  // its own client data: through the client routes, never through a panel key
  const own = await read(clientsPOST(req("/api/clients", "POST", { legal_name: "Sinder Client Ltd", claims: [{ field: "products_services", value: "OWNER-CLIENT-CLAIM-77", source_ref: "page 2" }] })));
  ok((await read(clientGET(req(`/api/clients/${own.j.client_id}`), ctx(String(own.j.client_id))))).text.includes("OWNER-CLIENT-CLAIM-77"), "original workspace: its own client is read through the client route");
  let keys = "";
  for (const key of ["jobs", "pursuits", "contacts", "accounts", "intel", "bd", "projects", "ptasks", "approvals", "websup"]) keys += (await read(panelGetPOST(req("/api/panel/get", "POST", { key, fresh: true })))).text;
  ok(!keys.includes("OWNER-CLIENT-CLAIM-77"), "original workspace: client data is not served through the shared panel keys");
  for (const key of ["Client Dossiers", "Prospects", "Deal Records", "Missions", "Campaigns", "Assertions", "Users"]) {
    const g = await read(panelGetPOST(req("/api/panel/get", "POST", { key })));
    ok(g.status === 500 && !g.text.includes("OWNER-CLIENT-CLAIM-77"), `original workspace: "${key}" is not a panel key`);
  }
  // a research row an acme account wrote to 'Panel Jobs' before the tab was closed is not adopted as the original workspace's memory
  TABS["Panel Jobs"] = [
    ["J1", "2026-11-01 10:00", "company_research", "", "Legacy Foreign Co (DEU)", "{}", "", "done", `Legacy Foreign Co sells ${M.sheet} through agents in East Africa and quotes ${M.price} per element on request.\n\nNext step: call.`, "", "2026-11-01 10:00", "web instant; ana@acme.test"],
    ["J2", "2026-11-01 11:00", "company_research", "", "Owner Researched Co (TUR)", "{}", "", "done", "Owner Researched Co makes valves and exports them to twelve countries across the region every year.\n\nNext step: call.", "", "2026-11-01 11:00", "web instant; op@sinder.test"],
  ];
  const bf = await backfillJobs(100);
  const mem = (await readAssertions(true)).filter((a) => (a.ws || "sinder") === "sinder");
  ok(bf.jobs === 1 && mem.length > 0 && !leaks(JSON.stringify(mem)).length && JSON.stringify(mem).includes("Owner Researched"), "research backfill: adopts the original workspace's own rows only");
  ok(!leaks((seenBy.sinder || []).join("\n")).length, "nothing acme owns appears in any response the original workspace received");

  // ------------------------------------------------------------------ and acme still has everything
  ACME();
  const mine = await read(dealGET(req(`/api/deal?id=${M.deal}`)));
  ok(mine.j.records.length === 2 && mine.text.includes(M.price) && (await read(clientGET(req(`/api/clients/${clientId}`), ctx(clientId)))).text.includes(M.sheet), "acme still reads its own deal, quote and client");
  ok((await read(assertionsGET(req("/api/panel/assertions")))).text.includes(M.memory) && (await read(campaignGET(req(`/api/outreach/campaign?id=${campId}`)))).text.includes(M.campaign), "acme still reads its own research memory and campaign");
  ACME_ADMIN();
  ok((await read(activityGET(req("/api/activity?limit=2000")))).j.rows.every((r: J) => /@acme\.test$/.test(r.email)), "acme's admin sees acme's activity only");

  console.log(fail ? `\n${fail} FAILED` : "\nall isolation tests passed");
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.log("FAIL crashed: " + String(e?.stack || e).slice(0, 800)); process.exit(1); });
