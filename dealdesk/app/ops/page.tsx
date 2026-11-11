import { notFound } from "next/navigation";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { readRanges } from "@/lib/sheets";
import { getSourceStatus, SOURCE_STATUS_LABEL } from "@/lib/data";

// Hidden operations page: not linked anywhere. Needs a signed-in session AND ?k=<OPS_KEY> (Vercel env var OPS_KEY).
// Without OPS_KEY set it does not exist (404). Shows the latest entries of the "App Log" tab.
export const dynamic = "force-dynamic";
export const metadata = { robots: { index: false, follow: false } };
const LE = "1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y";

export default async function Ops({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const p = await searchParams;
  const key = process.env.OPS_KEY;
  if (!key || p.k !== key || !verifySession((await cookies()).get("dd_session")?.value)) notFound();
  let rows: string[][] = [], err = "";
  try { rows = ((await readRanges(LE, ["'App Log'!A1:H3000"]))?.[0] || []).filter((r) => r[0] && r[0] !== "time"); } catch (e) { err = String(e).slice(0, 200); }
  const last = rows.slice(-300).reverse();
  const day = new Date(Date.now() - 864e5).toLocaleString("sv-SE", { timeZone: "Asia/Jerusalem" }).slice(0, 19);
  const recent = rows.filter((r) => r[0] >= day);
  const by = new Map<string, number>();
  for (const r of recent) by.set(`${r[2]} (${r[1]})`, (by.get(`${r[2]} (${r[1]})`) || 0) + 1);
  // collector status (data/leads/source_status.json): sources that are not OK come first, each with a text label
  const src = await getSourceStatus();
  const bad = (src?.sources || []).filter((x) => x.status !== "OK");
  const tone = (st: string) => (st === "OK" ? "text-muted" : st === "DEGRADED" || st === "STALE" ? "text-watch" : "text-no");
  const lvl = (l: string) => (l === "error" ? "text-no" : l === "warn" ? "text-watch" : "text-muted");
  return (
    <div className="space-y-4">
      <h1 className="text-xl font-bold text-navy">Operations log</h1>
      <p className="text-sm text-muted">Last 24 hours: {recent.length} events. {[...by.entries()].sort((a, b) => b[1] - a[1]).map(([k, v]) => `${k}: ${v}`).join(" | ") || "nothing logged."}</p>
      {err && <p className="text-sm text-no">Could not read the log: {err}</p>}
      <section className="space-y-2" aria-labelledby="src-status">
        <h2 id="src-status" className="text-base font-bold text-navy">Data sources</h2>
        {!src && <p className="text-sm text-watch">Status unknown: the source status file could not be read. Do not assume the sources are working.</p>}
        {src && <p className="text-sm text-muted">As of {src.generated || "unknown time"} (UTC): {bad.length ? `${bad.length} of ${src.sources.length} sources are not OK.` : `all ${src.sources.length} sources are OK.`}
          {src.merge?.status && src.merge.status !== "OK" ? ` The last merge was refused (${src.merge.warning || src.merge.error_class || src.merge.status}).` : ""}</p>}
        {src && (
          <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
            <table className="w-full text-xs">
              <thead><tr className="border-b border-line text-left uppercase text-muted"><th scope="col" className="px-3 py-2">Source</th><th scope="col" className="px-3 py-2">Status</th><th scope="col" className="px-3 py-2">Rows this run</th><th scope="col" className="px-3 py-2">Rows last good run</th><th scope="col" className="px-3 py-2">Last good run (UTC)</th><th scope="col" className="px-3 py-2">Error class</th><th scope="col" className="px-3 py-2">Note</th></tr></thead>
              <tbody>{src.sources.map((x) => (<tr key={x.source} className="border-b border-line/60 align-top"><td className="px-3 py-1.5 whitespace-nowrap font-bold">{x.source}</td><td className={`px-3 py-1.5 font-bold ${tone(x.status)}`}>{SOURCE_STATUS_LABEL[x.status] || `Unknown status (${x.status})`}</td><td className="px-3 py-1.5">{x.rows}</td><td className="px-3 py-1.5">{x.rows_last_good}</td><td className="px-3 py-1.5 whitespace-nowrap">{x.last_good_at || "never"}</td><td className="px-3 py-1.5">{x.error_class || ""}</td><td className="px-3 py-1.5 text-muted">{x.warning || ""}</td></tr>))}
                {!src.sources.length && <tr><td colSpan={7} className="px-4 py-6 text-center text-muted">No source has reported yet.</td></tr>}</tbody>
            </table>
          </div>
        )}
      </section>
      <h2 className="text-base font-bold text-navy">Application log</h2>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-xs">
          <thead><tr className="border-b border-line text-left uppercase text-muted"><th className="px-3 py-2">Time (Israel)</th><th className="px-3 py-2">Level</th><th className="px-3 py-2">Area</th><th className="px-3 py-2">Message</th><th className="px-3 py-2">Detail</th><th className="px-3 py-2">User</th><th className="px-3 py-2">Env</th><th className="px-3 py-2">Deploy</th></tr></thead>
          <tbody>{last.map((r, i) => (<tr key={i} className="border-b border-line/60 align-top"><td className="px-3 py-1.5 whitespace-nowrap">{r[0]}</td><td className={`px-3 py-1.5 font-bold ${lvl(r[1])}`}>{r[1]}</td><td className="px-3 py-1.5">{r[2]}</td><td className="px-3 py-1.5">{r[3]}</td><td className="px-3 py-1.5 text-muted">{r[4]}</td><td className="px-3 py-1.5">{r[5]}</td><td className="px-3 py-1.5">{r[6]}</td><td className="px-3 py-1.5">{r[7]}</td></tr>))}
            {!last.length && <tr><td colSpan={8} className="px-4 py-8 text-center text-muted">No events yet.</td></tr>}</tbody>
        </table>
      </div>
    </div>
  );
}
