// The two new write routes through their real handlers, with the real gate() and a signed test session; only
// next/headers, the sheet, the activity log and the mailer are in-memory fakes (tests/build-agent-test.mjs).
// POST /api/deal/feedback and POST /api/missions/[id]/step. No network, no model, nothing is sent.
import { NextRequest } from "next/server";
import { signSession } from "@/lib/auth";
import { JAR } from "./mocks/next-headers";
import { TABS } from "./mocks/sheets";
import { POST as feedbackPOST } from "@/app/api/deal/feedback/route";
import { POST as stepPOST } from "@/app/api/missions/[id]/step/route";
import { GET as missionsGET, POST as missionsPOST } from "@/app/api/missions/route";

let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };
process.env.AUTH_SECRET = "test-secret";
process.env.GOOGLE_SERVICE_ACCOUNT_JSON = "{}"; // "Sheets is configured": every read and write below goes to the in-memory tabs

const as = (email: string, role: "viewer" | "analyst" | "admin", ws: string) => { JAR.dd_session = signSession(email, role, email, 1, ws); };
const req = (path: string, method = "GET", body?: unknown) => new NextRequest("http://localhost" + path, { method, ...(body === undefined ? {} : { body: JSON.stringify(body), headers: { "content-type": "application/json" } }) });
const ctx = (id: string) => ({ params: Promise.resolve({ id }) });
type J = Record<string, any>;  // eslint-disable-line @typescript-eslint/no-explicit-any
const read = async (r: Response) => ({ status: r.status, j: (await r.json().catch(() => ({}))) as J });
const rows = () => (TABS["Outcomes"] || []).map((x) => JSON.parse(String(x[6])) as J);

(async () => {
  // ---- feedback
  JAR.dd_session = undefined;
  ok((await read(await feedbackPOST(req("/api/deal/feedback", "POST", { deal_id: "T-1", reason: "timing" })))).status === 401, "feedback, signed out: 401");
  as("v@acme.test", "viewer", "acme");
  ok((await read(await feedbackPOST(req("/api/deal/feedback", "POST", { deal_id: "T-1", reason: "timing" })))).status === 403 && rows().length === 0, "feedback, viewer: 403 and nothing stored");
  as("ana@acme.test", "analyst", "acme");
  ok((await read(await feedbackPOST(req("/api/deal/feedback", "POST", { deal_id: "T-1", reason: "because I say so" })))).status === 400
    && (await read(await feedbackPOST(req("/api/deal/feedback", "POST", { reason: "timing" })))).status === 400 && rows().length === 0, "feedback: a reason outside the fixed list, or no deal, is refused (400)");
  const good = await read(await feedbackPOST(req("/api/deal/feedback", "POST", { deal_id: "T-1", reason: "uncompetitive_price", workspace: "sinder", actor: "boss@sinder.pro" })));
  const e = rows()[0];
  ok(good.status === 200 && good.j.ok && rows().length === 1 && e.type === "feedback" && e.reason === "uncompetitive_price" && e.case_id === "T-1", "feedback, analyst: stored as one ledger event with the reason");
  ok(e.workspace === "acme" && e.actor === "ana@acme.test" && e.rights_scope === "own" && String(TABS["Outcomes"][0][1]) === "acme", "the workspace and the actor come from the session, never from the request body");
  as("boss@acme.test", "admin", "acme");
  ok((await read(await feedbackPOST(req("/api/deal/feedback", "POST", { deal_id: "T-1", reason: "wrong_spec" })))).status === 200 && rows().length === 2, "feedback, admin (the owner): stored");

  // ---- one mission step
  JAR.dd_session = undefined;
  ok((await read(await stepPOST(req("/api/missions/MIS-000000000000/step", "POST"), ctx("MIS-000000000000")))).status === 401, "step, signed out: 401");
  as("v@acme.test", "viewer", "acme");
  ok((await read(await stepPOST(req("/api/missions/MIS-000000000000/step", "POST"), ctx("MIS-000000000000")))).status === 403, "step, viewer: 403");
  as("ana@acme.test", "analyst", "acme");
  ok((await read(await stepPOST(req("/api/missions/MIS-000000000000/step", "POST"), ctx("MIS-000000000000")))).status === 404 && (await read(await stepPOST(req("/api/missions/x/step", "POST"), ctx("../x")))).status === 400,
    "step, analyst: an unknown mission is 404, an unreadable id is 400");
  // a mission with no deal: the first step asks the owner which deal, without reading any index
  const made = await read(await missionsPOST(req("/api/missions", "POST", { type: "supply_winner", goal: "Supply the winner of a fixture award", cost_budget_usd: 2 })));
  const id = String(made.j.mission?.id || "");
  ok(made.status === 200 && /^MIS-/.test(id) && made.j.mission.tasks === 0 && Array.isArray(made.j.mission.task_list), "a mission is recorded with no task");
  const s1 = await read(await stepPOST(req(`/api/missions/${id}/step`, "POST"), ctx(id)));
  ok(s1.status === 200 && s1.j.ok && s1.j.ran === null && s1.j.mission.status === "needs_owner" && /Which deal/.test(s1.j.mission.next_decision) && s1.j.mission.task_list.length === 8,
    "one call plans the 8 tasks and stops at needs_owner with the question; no task ran");
  ok(s1.j.mission.task_list[0].step === "award_verification" && s1.j.mission.task_list[0].status === "queued" && s1.j.mission.task_list[0].persona.includes("Evidence") && s1.j.mission.spent_usd === 0, "the answer lists each task with its status and the persona of its role");
  const s2 = await read(await stepPOST(req(`/api/missions/${id}/step`, "POST"), ctx(id)));
  const taskRows = (TABS["Missions"] || []).filter((x) => x[3] === "task").length;
  ok(s2.j.mission.status === "needs_owner" && s2.j.mission.task_list.length === 8 && taskRows === 8, "a second call asks the same question and adds no task row");
  as("eve@other.test", "admin", "other");
  ok((await read(await stepPOST(req(`/api/missions/${id}/step`, "POST"), ctx(id)))).status === 404 && ((await read(await missionsGET(req("/api/missions")))).j.missions || []).length === 0, "another workspace cannot run or see the mission");
  if (fail) { console.log(`${fail} failed`); process.exit(1); }
})();
