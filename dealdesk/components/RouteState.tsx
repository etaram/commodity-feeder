"use client";
import { useCallback, useEffect, useState } from "react";

// Route state, missions and feedback for one deal. Reads /api/deal/route-state and /api/missions. Writes: "Create
// mission" (records a mission, starts nothing), "Run next step" (POST /api/missions/ID/step: one step per press, no
// loop, no model, nothing sent) and the feedback reason (POST /api/deal/feedback). A value the deal file does not
// hold is shown as "unknown".
type Blocker = { gate: string; text: string; decisive: boolean };
type Missing = { gate: string; question: string; why: string; cost: number };
type Task = { kind: string; question: string; why: string } | null;
type View = {
  evaluation: { state: string; route_type: string; blockers: Blocker[]; missing: Missing[]; days_left: number | null; source_families: number; exact_fit: boolean;
    profit_statement: string; economics: { margin: number | null; price_type: string } };
  priority: { known: number; weighted_sum: number } | null;
  next_task: Task;
  supplier: { supplier: string | null; basis: string };
  contact: { needs_owner_approval: boolean; conversation_mode: boolean };
  sanctions?: { status: string; label: string; candidates: { name: string }[] };
  not_in_deal_file: string[];
};
type TaskRow = { key: string; step: string; role: string; persona: string; status: string; attempt: number; review: string; summary: string; sources: string[]; open_questions: string[]; last_error: string };
type MissionRow = { id: string; type: string; goal: string; status: string; cost_budget_usd: number; spent_usd: number; tasks: number; next_decision: string; created_at: string; task_list?: TaskRow[] };
// the fixed reason list of lib/outcomes.ts (REASONS); the server refuses anything else
const REASONS: [string, string][] = [["right_product", "Right product"], ["wrong_spec", "Wrong specification"], ["already_purchased", "Already purchased"], ["timing", "Timing"], ["no_contact", "No contact"],
  ["uncompetitive_price", "Uncompetitive price"], ["logistics", "Logistics"], ["financing", "Financing"], ["regulatory", "Regulatory"], ["poor_signal", "Poor signal"], ["not_interested", "Not interested"], ["other", "Other"]];
const TASK_STATUS: Record<string, string> = { queued: "Queued", running: "Running", completed: "Completed", failed: "Failed", cancelled: "Cancelled" };
const TASK_CHIP: Record<string, string> = { queued: "bg-paper text-muted", running: "bg-watchbg text-watch", completed: "bg-gobg text-go", failed: "bg-nobg text-no", cancelled: "bg-paper text-muted" };
const SANCTIONS_STATUS: Record<string, string> = { NOT_CHECKED: "Not checked", CHECKED_NO_ISSUE: "Checked, no candidate match", FAILED: "Alert: candidate match", STALE: "Not checked (list out of date)", VERIFIED: "Verified by a qualified person" };
const TERMINAL = ["completed", "failed", "cancelled"];

const STATE_LABEL: Record<string, string> = { INELIGIBLE: "Ineligible", MISMATCH: "Mismatch", NEEDS_EVIDENCE: "Needs evidence", RESEARCH: "Research", MONITOR: "Monitor",
  READY_FOR_OWNER_REVIEW: "Ready for owner review", READY_FOR_AUTHORIZED_CONTACT: "Ready for authorized contact", ACTIVE: "Active", STOPPED: "Stopped" };
const STATE_MEANS: Record<string, string> = { INELIGIBLE: "This route cannot be used.", MISMATCH: "A mandatory requirement is contradicted.", NEEDS_EVIDENCE: "A requirement or a core claim is not evidenced.",
  RESEARCH: "A basic input is missing.", MONITOR: "Nothing to do until an outside event.", READY_FOR_OWNER_REVIEW: "The checks passed; the owner decides.",
  READY_FOR_AUTHORIZED_CONTACT: "The checks passed and an owner approval is on file.", ACTIVE: "Contact is recorded.", STOPPED: "Stopped by a sanctions alert or by the owner." };
const STATE_CHIP: Record<string, string> = { INELIGIBLE: "bg-nobg text-no", MISMATCH: "bg-nobg text-no", STOPPED: "bg-nobg text-no", NEEDS_EVIDENCE: "bg-watchbg text-watch", RESEARCH: "bg-watchbg text-watch",
  MONITOR: "bg-paper text-muted", READY_FOR_OWNER_REVIEW: "bg-[#E6ECF3] text-blue", READY_FOR_AUTHORIZED_CONTACT: "bg-gobg text-go", ACTIVE: "bg-gobg text-go" };
const NO_TASK: Record<string, string> = { READY_FOR_OWNER_REVIEW: "None. The owner's decision is the next step.", READY_FOR_AUTHORIZED_CONTACT: "None. The route is ready.", ACTIVE: "None. Contact is under way.",
  INELIGIBLE: "None. The route is closed.", MISMATCH: "None. The route is closed for this supplier.", STOPPED: "None. The route is stopped." };
const MISSION_TYPE: Record<string, string> = { win_tender: "Win a tender", supply_winner: "Supply the winner", client_bd: "Client development", strategic_signal: "Strategic signal" };
const MISSION_STATUS: Record<string, string> = { queued: "Queued", running: "Running", waiting_on_external: "Waiting on an outside event", needs_owner: "Needs the owner", paused_on_risk: "Paused on a risk",
  completed: "Completed", failed: "Failed", cancelled: "Cancelled" };
const label = (v: string) => { const t = v.replace(/_/g, " "); return t.charAt(0).toUpperCase() + t.slice(1); };
const usd = (v: number) => `${v.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USD`;
const H2 = "text-sm font-bold uppercase tracking-wide text-muted", CARD = "rounded-xl border border-line bg-white p-5 shadow-sm", SUB = "text-[11px] font-bold uppercase tracking-wide text-muted";
const INPUT = "rounded-md border border-line bg-white px-2.5 py-1.5 text-sm";

function Fact({ name, value }: { name: string; value: string }) {
  return <div>{name}: <b className={value === "unknown" ? "font-semibold text-muted" : "text-ink"}>{value}</b></div>;
}

function RouteCard({ id }: { id: string }) {
  const [v, setV] = useState<View | null>(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let live = true;
    fetch(`/api/deal/route-state?id=${encodeURIComponent(id)}`).then(async (r) => {
      const j = await r.json().catch(() => ({}));
      if (!live) return;
      if (r.ok && j.ok) setV(j as View);
      else setErr(r.status === 403 ? "The route state needs the analyst role." : r.status === 401 ? "Sign in again to see the route state." : `The route state could not be read${j.error ? `: ${j.error}` : "."}`);
    }).catch(() => { if (live) setErr("The route state could not be read."); });
    return () => { live = false; };
  }, [id]);

  if (err) return <section className={CARD}><h2 className={H2}>Route state</h2><p className="mt-2 text-sm text-muted" role="status">{err}</p></section>;
  if (!v) return <section className={CARD}><h2 className={H2}>Route state</h2><p className="mt-2 text-sm text-muted" role="status">Reading the deal file...</p></section>;
  const e = v.evaluation, blockers = e.blockers.slice(0, 3), missing = e.missing.slice(0, 5);
  return (
    <section className={CARD} aria-label="Route state">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className={H2}>Route state</h2>
        <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${STATE_CHIP[e.state] || "bg-paper text-muted"}`}>{STATE_LABEL[e.state] || label(e.state.toLowerCase())}</span>
        <span className="text-xs text-muted">{STATE_MEANS[e.state] || ""}</span>
      </div>
      <div className="mt-3 grid grid-cols-1 gap-x-6 gap-y-1 text-sm md:grid-cols-3">
        <Fact name="Route" value={label(e.route_type)} />
        <Fact name="Supplier" value={v.supplier.supplier ? `${v.supplier.supplier} (${v.supplier.basis})` : v.supplier.basis === "none recorded" ? "unknown" : `unknown (${v.supplier.basis})`} />
        <Fact name="Exact fit" value={e.exact_fit ? "Yes" : "Not shown"} />
        <Fact name="Days to the deadline" value={e.days_left === null ? "unknown" : String(e.days_left)} />
        <Fact name="Independent source families" value={String(e.source_families)} />
        <Fact name="Margin" value={e.economics.margin === null ? "unknown" : `${e.economics.margin.toLocaleString("en-US")} (${e.profit_statement === "authoritative" ? "from a live quote" : "not a profit statement"})`} />
      </div>

      <div className="mt-4 grid grid-cols-1 gap-5 md:grid-cols-2">
        <div>
          <div className={SUB}>Top blockers</div>
          {blockers.length ? (
            <ul className="mt-1 space-y-1 text-sm">
              {blockers.map((b, i) => <li key={i}><b>{b.decisive ? "Blocker" : "Limit"}</b> ({label(b.gate)}): {b.text}</li>)}
            </ul>
          ) : <p className="mt-1 text-sm text-muted">None.</p>}
          {e.blockers.length > blockers.length && <p className="mt-1 text-xs text-muted">{e.blockers.length - blockers.length} more not shown.</p>}
        </div>
        <div>
          <div className={SUB}>What is missing</div>
          {missing.length ? (
            <ul className="mt-1 space-y-1 text-sm">
              {missing.map((m, i) => <li key={i}>{label(m.why)} <span className="text-xs text-muted">({label(m.gate)})</span></li>)}
            </ul>
          ) : <p className="mt-1 text-sm text-muted">Nothing.</p>}
          {e.missing.length > missing.length && <p className="mt-1 text-xs text-muted">{e.missing.length - missing.length} more not shown.</p>}
        </div>
      </div>

      <div className="mt-4 rounded-lg border border-line bg-paper px-4 py-3">
        <div className={SUB}>Next cheapest task</div>
        {v.next_task ? (
          <>
            <p className="mt-0.5 text-sm font-semibold">{v.next_task.question}</p>
            <p className="text-xs text-muted">Why: {v.next_task.why}.{v.next_task.kind === "confirm_legal" ? " Record the answer in the deal as a requirement named \"Legal: data rights\" or \"Legal: representation\", with its evidence." : ""}</p>
          </>
        ) : <p className="mt-0.5 text-sm">{NO_TASK[e.state] || "None."}</p>}
      </div>

      <p className="mt-3 text-sm">{v.contact.needs_owner_approval
        ? <><b>Contact needs owner approval.</b> Every outgoing message is approved one by one; conversation mode is off.</>
        : <b>The send policy could not be confirmed. Treat every message as needing owner approval.</b>}</p>
      <p className="mt-1 text-sm">Sanctions screen: <b className={v.sanctions?.status === "FAILED" ? "text-no" : "text-ink"}>{SANCTIONS_STATUS[v.sanctions?.status || "NOT_CHECKED"] || "Not checked"}</b>
        {v.sanctions?.label ? <span className="text-xs text-muted"> {label(v.sanctions.label)}.</span> : null}
        <span className="text-xs text-muted"> A name screen is a lead to verify, never a clearance.</span></p>
      <p className="mt-1 text-xs text-muted">Built from this deal&apos;s saved records by fixed rules; no model is used and this is not a likelihood of winning. Not in the deal file, so unknown here: {v.not_in_deal_file.join(", ")}.</p>
    </section>
  );
}

function Missions({ id }: { id: string }) {
  const [rows, setRows] = useState<MissionRow[] | null>(null);
  const [err, setErr] = useState("");
  const [open, setOpen] = useState(false);
  const [type, setType] = useState("win_tender");
  const [goal, setGoal] = useState("");
  const [budget, setBudget] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [stepping, setStepping] = useState("");
  const [shown, setShown] = useState<Record<string, boolean>>({});

  // One press runs one step and then stops. Nothing here calls it again by itself.
  async function runStep(missionId: string) {
    setStepping(missionId); setMsg("");
    try {
      const r = await fetch(`/api/missions/${encodeURIComponent(missionId)}/step`, { method: "POST" });
      const j = await r.json().catch(() => ({}));
      if (j.mission) { setRows((cur) => (cur || []).map((m) => (m.id === missionId ? (j.mission as MissionRow) : m))); setShown((x) => ({ ...x, [missionId]: true })); }
      setMsg(r.status === 403 ? "View-only account: running a step needs the analyst role." : r.status === 401 ? "Sign in again to run a step."
        : j.mission ? `${j.ran ? "Ran one step" : "No step ran"}: ${j.note || j.error || ""}` : j.error || "The step could not be run.");
    } catch { setMsg("The step could not be run."); }
    setStepping("");
  }

  const load = useCallback(async () => {
    try {
      const r = await fetch(`/api/missions?deal_id=${encodeURIComponent(id)}`);
      const j = await r.json().catch(() => ({}));
      if (r.ok && j.ok) { setRows(j.missions as MissionRow[]); setErr(""); }
      else setErr(r.status === 403 ? "Missions need the analyst role." : r.status === 401 ? "Sign in again to see missions." : `Missions could not be read${j.error ? `: ${j.error}` : "."}`);
    } catch { setErr("Missions could not be read."); }
  }, [id]);
  useEffect(() => { load(); }, [load]);

  async function create(ev: React.FormEvent) {
    ev.preventDefault();
    const b = Number(budget);
    if (!goal.trim()) { setMsg("Write the goal."); return; }
    if (budget.trim() === "" || !Number.isFinite(b) || b < 0) { setMsg("Enter the cost budget in USD (0 or more)."); return; }
    setBusy(true); setMsg("");
    try {
      const r = await fetch("/api/missions", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ type, goal, deal_id: id, cost_budget_usd: b }) });
      const j = await r.json().catch(() => ({}));
      if (r.ok && j.ok) { setMsg(j.created ? "Mission recorded. No task has started." : "This mission already exists."); setGoal(""); setBudget(""); setOpen(false); await load(); }
      else setMsg(r.status === 403 ? "View-only account: creating a mission needs the analyst role." : j.error || "The mission could not be saved.");
    } catch { setMsg("The mission could not be saved."); }
    setBusy(false);
  }

  return (
    <section className={CARD} aria-label="Missions">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className={H2}>Missions</h2>
        {!err && <button type="button" onClick={() => { setOpen(!open); setMsg(""); }} aria-expanded={open} className="rounded-md border border-accent px-3 py-1.5 text-xs font-semibold text-accent hover:bg-accent hover:text-white">{open ? "Cancel" : "Create mission"}</button>}
      </div>
      <p className="mt-1 text-xs text-muted">A mission records a goal and a cost budget for this deal. Creating one starts no task. &quot;Run next step&quot; runs one step by fixed rules: no model is called, nothing is sent, and a step that needs a person or an outside answer stops with its question.</p>
      {open && (
        <form onSubmit={create} className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-[12rem_1fr_9rem_auto] md:items-end">
          <label className="text-xs font-semibold text-muted">Type
            <select value={type} onChange={(x) => setType(x.target.value)} className={`${INPUT} mt-1 block w-full`}>
              {Object.entries(MISSION_TYPE).map(([k, t]) => <option key={k} value={k}>{t}</option>)}
            </select>
          </label>
          <label className="text-xs font-semibold text-muted">Goal
            <input value={goal} onChange={(x) => setGoal(x.target.value)} maxLength={500} required className={`${INPUT} mt-1 block w-full`} />
          </label>
          <label className="text-xs font-semibold text-muted">Cost budget (USD)
            <input value={budget} onChange={(x) => setBudget(x.target.value)} inputMode="decimal" required className={`${INPUT} mt-1 block w-full`} />
          </label>
          <button type="submit" disabled={busy} className="rounded-md bg-accent px-3 py-2 text-xs font-bold text-white hover:bg-blue disabled:opacity-40">{busy ? "Saving..." : "Save mission"}</button>
        </form>
      )}
      {msg && <p className="mt-2 text-sm" role="status">{msg}</p>}
      {err ? <p className="mt-2 text-sm text-muted" role="status">{err}</p>
        : rows === null ? <p className="mt-2 text-sm text-muted" role="status">Reading missions...</p>
        : rows.length === 0 ? <p className="mt-2 text-sm text-muted">No missions for this deal yet.</p>
        : (
          <ul className="mt-3 divide-y divide-line/60">
            {rows.map((m) => (
              <li key={m.id} className="py-2 text-sm">
                <div className="font-semibold">{m.goal}</div>
                <div className="text-xs text-muted">{MISSION_TYPE[m.type] || label(m.type)} · Status: <b className="text-ink">{MISSION_STATUS[m.status] || label(m.status)}</b> · {usd(m.spent_usd)} spent of {usd(m.cost_budget_usd)} · {m.tasks} {m.tasks === 1 ? "task" : "tasks"} · {m.created_at.slice(0, 10)} · {m.id}</div>
                {m.next_decision && <div className="mt-0.5 text-xs"><b>Next decision:</b> {m.next_decision}</div>}
                <div className="mt-1.5 flex flex-wrap items-center gap-2">
                  {!TERMINAL.includes(m.status) && <button type="button" onClick={() => runStep(m.id)} disabled={!!stepping} className="rounded-md bg-accent px-3 py-1.5 text-xs font-bold text-white hover:bg-blue disabled:opacity-40">{stepping === m.id ? "Running one step..." : "Run next step"}</button>}
                  {!!m.task_list?.length && <button type="button" onClick={() => setShown((x) => ({ ...x, [m.id]: !x[m.id] }))} aria-expanded={!!shown[m.id]} className="rounded-md border border-line px-3 py-1.5 text-xs font-semibold text-ink hover:bg-paper">{shown[m.id] ? "Hide tasks" : `Show tasks (${m.task_list.length})`}</button>}
                </div>
                {shown[m.id] && !!m.task_list?.length && (
                  <ol className="mt-2 space-y-2 border-l-2 border-line pl-3">
                    {m.task_list.map((t) => (
                      <li key={t.key} className="text-xs">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="text-sm font-semibold">{label(t.step)}</span>
                          <span className={`rounded-full px-2 py-0.5 font-bold ${TASK_CHIP[t.status] || "bg-paper text-muted"}`}>{TASK_STATUS[t.status] || label(t.status)}</span>
                          <span className="text-muted">{t.persona}</span>
                          {t.review && <span className="text-muted">Review: {t.review}</span>}
                        </div>
                        {t.summary && <p className="mt-0.5 text-sm">{t.summary}</p>}
                        {!t.summary && t.last_error && <p className="mt-0.5 text-muted">Not accepted: {t.last_error}</p>}
                        {t.open_questions.length > 0 && <p className="mt-0.5">Open: {t.open_questions.join(" · ")}</p>}
                        {t.sources.length > 0 && <p className="mt-0.5 break-words text-muted">Sources: {t.sources.map((src, i) => <span key={i}>{i ? " · " : ""}{/^https?:\/\//.test(src) ? <a href={src} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">{src}</a> : src}</span>)}</p>}
                      </li>
                    ))}
                  </ol>
                )}
              </li>
            ))}
          </ul>
        )}
    </section>
  );
}

function Feedback({ id }: { id: string }) {
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  async function save(ev: React.FormEvent) {
    ev.preventDefault();
    if (!reason) { setMsg("Pick a reason."); return; }
    setBusy(true); setMsg("");
    try {
      const r = await fetch("/api/deal/feedback", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ deal_id: id, reason }) });
      const j = await r.json().catch(() => ({}));
      setMsg(r.ok && j.ok ? "Feedback saved." : r.status === 403 ? "View-only account: feedback needs the analyst role." : r.status === 401 ? "Sign in again to save feedback." : j.error || "The feedback could not be saved.");
      if (r.ok && j.ok) setReason("");
    } catch { setMsg("The feedback could not be saved."); }
    setBusy(false);
  }
  return (
    <section className={CARD} aria-label="Feedback">
      <h2 className={H2}>Feedback on this deal</h2>
      <form onSubmit={save} className="mt-2 flex flex-wrap items-end gap-3">
        <label className="text-xs font-semibold text-muted">Reason
          <select value={reason} onChange={(x) => setReason(x.target.value)} className={`${INPUT} mt-1 block`}>
            <option value="">Pick a reason</option>
            {REASONS.map(([k, t]) => <option key={k} value={k}>{t}</option>)}
          </select>
        </label>
        <button type="submit" disabled={busy || !reason} className="rounded-md border border-accent px-3 py-2 text-xs font-semibold text-accent hover:bg-accent hover:text-white disabled:opacity-40">{busy ? "Saving..." : "Save feedback"}</button>
        {msg && <span className="text-sm" role="status">{msg}</span>}
      </form>
      <p className="mt-1 text-xs text-muted">Stored in the outcome record with your name and the time. It changes no deal record and no ranking.</p>
    </section>
  );
}

export default function RouteState({ id }: { id: string }) {
  return <><RouteCard id={id} /><Missions id={id} /><Feedback id={id} /></>;
}
