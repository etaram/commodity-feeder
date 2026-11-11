// Client API isolation and review permissions, through the real route handlers (F02, spec section 15).
// The handlers run with the real gate() and a signed test session; only next/headers and the sheet are in-memory fakes
// (tests/build-agent-test.mjs). No network, no model.
import { NextRequest } from "next/server";
import { signSession } from "@/lib/auth";
import { JAR } from "./mocks/next-headers";
import { GET as listGET, POST as createPOST } from "@/app/api/clients/route";
import { GET as oneGET, PUT as onePUT } from "@/app/api/clients/[id]/route";
import { POST as ingestPOST } from "@/app/api/clients/[id]/ingest/route";
import { GET as prospectsGET } from "@/app/api/clients/[id]/prospects/route";
import { POST as targetsPOST } from "@/app/api/clients/[id]/targets/route";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.AUTH_SECRET = "test-secret";

const as = (email: string, role: "viewer" | "analyst" | "admin", ws: string) => { JAR.dd_session = signSession(email, role, email, 1, ws); };
const req = (path: string, method = "GET", body?: unknown) => new NextRequest("http://localhost" + path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { "content-type": "application/json" } }) });
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });
type J = Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const read = async (r: Response) => ({ status: r.status, j: (await r.json().catch(() => ({}))) as J });
const A = () => as("ana@acme.test", "analyst", "acme"), ADMIN = () => as("boss@acme.test", "admin", "acme"), B = () => as("eve@other.test", "admin", "other");

(async () => {
  // ---- signed out, low role, forged session
  JAR.dd_session = undefined;
  ok((await read(await listGET())).status === 401 && (await read(await oneGET(req("/api/clients/CL-AAAAAAAA"), ctx("CL-AAAAAAAA")))).status === 401, "signed out: the client API answers 401");
  as("v@acme.test", "viewer", "acme");
  ok((await read(await listGET())).status === 403 && (await read(await createPOST(req("/api/clients", "POST", { legal_name: "X Ltd" })))).status === 403, "a viewer cannot list or create clients (403)");
  JAR.dd_session = signSession("eve@other.test", "admin", "Eve", 1, "other").split(".")[0].replace(/.$/, "A") + "." + "x".repeat(43);
  ok((await read(await listGET())).status === 401, "a session whose payload was altered is refused");

  // ---- create in the session's workspace; the body cannot choose another one
  A();
  const made = await read(await createPOST(req("/api/clients", "POST", { legal_name: "Alpha Membranes Ltd", jurisdiction: "Israel", country: "ISR", website: "https://www.alpha-membranes.example/about", business_objective: "Find EPC partners in East Africa", representation_status: "in_discussion", ws: "other", workspace: "other",
    claims: [{ field: "products_services", value: "Membrane elements for water treatment", source_ref: "slide 2" }, { field: "certifications", value: "ISO 9001 certified", source_ref: "slide 3" }, { field: "markets", value: "no source" }] })));
  const id = String(made.j.client_id || "");
  ok(made.status === 201 && /^CL-/.test(id) && made.j.dossier.identity.jurisdiction === "Israel" && made.j.dossier.identity.official_domains.includes("alpha-membranes.example") && made.j.dossier.business_objective.startsWith("Find EPC") && made.j.dossier.representation_status === "in_discussion",
    "create stores legal name, jurisdiction, website, business objective and representation status");
  ok(made.j.rejected.length === 1 && made.j.dossier.claims.every((c: J) => c.approved === false), "a claim without a source is rejected; nothing is approved at creation");
  const mine = await read(await listGET());
  ok(mine.j.clients.length === 1 && mine.j.clients[0].client_id === id && mine.j.clients[0].review_state === "facts_under_review", "the creator's workspace lists the client with its review state");
  B();
  const theirs = await read(await listGET());
  ok(theirs.status === 200 && theirs.j.clients.length === 0, "another workspace's list does not contain it (the workspace in the body was ignored)");

  // ---- every route answers 404 for another workspace's client id, the same as for an id that does not exist
  const tiny = Buffer.from("%PDF-1.4\n").toString("base64");
  const cross = {
    get: await read(await oneGET(req(`/api/clients/${id}`), ctx(id))),
    put: await read(await onePUT(req(`/api/clients/${id}`, "PUT", { name: "Taken over", status: "active" }), ctx(id))),
    ingest: await read(await ingestPOST(req(`/api/clients/${id}/ingest`, "POST", { file: tiny, filename: "x.pdf" }), ctx(id))),
    prospects: await read(await prospectsGET(req(`/api/clients/${id}/prospects`), ctx(id))),
    targets: await read(await targetsPOST(req(`/api/clients/${id}/targets`, "POST", { action: "profiles" }), ctx(id))),
  };
  for (const [k, v] of Object.entries(cross)) ok(v.status === 404 && v.j.ok === false && !JSON.stringify(v.j).includes("Alpha"), `${k}: another workspace's client id returns 404 and no content`);
  const ghost = await read(await oneGET(req("/api/clients/CL-ZZZZZZZZ"), ctx("CL-ZZZZZZZZ")));
  ok(ghost.status === 404 && JSON.stringify(ghost.j) === JSON.stringify(cross.get.j), "a real id of another workspace and a guessed id are indistinguishable");
  for (const bad of ["../../etc", "CL-", "cl-aaaaaaaa", id + "'--"]) ok((await read(await oneGET(req("/api/clients/x"), ctx(bad)))).status === 404, `malformed id ${JSON.stringify(bad)} returns 404`);
  A();
  const still = await read(await oneGET(req(`/api/clients/${id}`), ctx(id)));
  ok(still.status === 200 && still.j.dossier.name === "Alpha Membranes Ltd" && still.j.dossier.status === "draft" && still.j.version === 1, "the other workspace's attempts changed nothing");
  ok(still.j.outreach.enabled === false && /approved conversation/.test(still.j.outreach.reason), "the client page reports outreach as not available");

  // ---- approval is a server-side permission: admin or the client's representative
  const prod = still.j.dossier.claims.find((c: J) => c.field === "products_services").id, cert = still.j.dossier.claims.find((c: J) => c.field === "certifications").id;
  let r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { update_claims: [{ id: prod, approved: true }] }), ctx(id)));
  ok(r.status === 403 && still.j.can_approve === false, "an analyst who is not the client's representative cannot approve a claim (403)");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { mandate: { allowed_claims: [prod], target_markets: ["KEN"] } }), ctx(id)));
  ok(r.status === 403, "nor change the mandate");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { representatives: ["ana@acme.test"] }), ctx(id)));
  ok(r.status === 403, "nor name itself the representative");
  r = await read(await oneGET(req(`/api/clients/${id}`), ctx(id)));
  ok(r.j.outreach_claims.length === 0 && r.j.dossier.claims.every((c: J) => !c.approved) && !r.j.dossier.mandate, "after the refused calls no claim is approved and no mandate exists");

  ADMIN();
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { mandate: { allowed_claims: [prod, cert, "K-NOPE"], target_markets: ["KEN", "TZA"], exclusions: ["Existing distributor in Uganda"], permitted_sender: { name: "Dana", email: "dana@acme.test", org: "Acme" }, limits: { max_accounts: 20, max_messages_per_day: 5, valid_until: "2027-01-31" } } }), ctx(id)));
  ok(r.status === 200 && r.j.dossier.mandate.allowed_claims.length === 0 && r.j.errors.length === 3 && r.j.dossier.mandate.target_markets.length === 2, "an unapproved claim cannot be made an allowed claim, even by an admin (dropped, with the reason)");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { update_claims: [{ id: prod, approved: true }], representatives: ["ana@acme.test"] }), ctx(id)));
  ok(r.status === 200 && r.j.outreach_claims.length === 1 && r.j.outreach_claims[0] === prod, "an admin approves a claim and names the representative");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { mandate: { allowed_claims: [prod] } }), ctx(id)));
  ok(r.j.dossier.mandate.allowed_claims.join() === prod && r.j.dossier.mandate.permitted_sender.email === "dana@acme.test" && r.j.dossier.mandate.limits.max_accounts === 20, "the approved claim can now be selected; the rest of the mandate is kept");
  A();
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { update_claims: [{ id: cert, approved: true }] }), ctx(id)));
  ok(r.status === 200 && r.j.outreach_claims.includes(cert) && r.j.can_approve === true, "the named representative can approve");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { update_claims: [{ id: prod, value: "Membrane elements and pressure vessels for water treatment" }] }), ctx(id)));
  const edited = r.j.dossier.claims.find((c: J) => c.id === prod);
  ok(edited.approved === false && edited.original_value === "Membrane elements for water treatment" && !r.j.outreach_claims.includes(prod) && !r.j.dossier.mandate.allowed_claims.includes(prod), "editing an approved claim withdraws the approval and removes it from the mandate's allowed claims");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { update_claims: [{ id: cert, rejected: true, reject_reason: "certificate expired" }] }), ctx(id)));
  ok(r.j.dossier.claims.find((c: J) => c.id === cert).rejected === true && !r.j.outreach_claims.includes(cert), "a rejected claim leaves the outreach set");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { update_claims: [{ id: cert, approved: true }] }), ctx(id)));
  ok(!r.j.dossier.claims.find((c: J) => c.id === cert).approved, "and cannot be approved while rejected");
  as("other-analyst@acme.test", "analyst", "acme");
  r = await read(await onePUT(req(`/api/clients/${id}`, "PUT", { status: "active" }), ctx(id)));
  ok(r.status === 403, "an analyst cannot move a client to approved");
  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})().catch((e) => { console.log("FAIL crashed: " + (e?.stack || e)); process.exit(1); });
