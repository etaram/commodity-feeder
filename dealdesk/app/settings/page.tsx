import { getSources, num } from "@/lib/data";
import { sheetsEnabled } from "@/lib/sheets";
import { facet } from "@/lib/index";
import FilterBar from "@/components/FilterBar";

export const dynamic = "force-dynamic";

export default async function Settings({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const p = await searchParams;
  const sources = await getSources();
  const allRows = sources.filter((s) => s.source).sort((a, b) => num(b.rows) - num(a.rows));
  const rows = allRows.filter((s) => (!p.state || s.note === p.state) && (!p.q || s.source.toLowerCase().includes(p.q.toLowerCase())));
  const failing = allRows.filter((s) => s.note !== "OK");
  const sheets = sheetsEnabled();
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-navy">System status</h1>
      <div className="grid gap-3 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
          <div className="text-sm font-bold">Decisions and research jobs</div>
          <p className="mt-1 text-sm text-muted">{sheets ? "Connected. Go / Watch / No and agent jobs are written straight to the engine." : "Not connected yet: add the GOOGLE_SERVICE_ACCOUNT_JSON environment variable in Vercel (same value as the GitHub Actions secret) to enable decisions and agent jobs from this site."}</p>
        </div>
        <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
          <div className="text-sm font-bold">Where the data comes from</div>
          <p className="mt-1 text-sm text-muted">Official procurement portals and APIs only, collected every 4 hours (Israel daily), scored by the deal engine, enriched with World Bank prices, freight indices, trade-agreement duties, US federal awards and world press.</p>
        </div>
      </div>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1"><b>{allRows.length - failing.length}</b> of <b>{allRows.length}</b> sources delivered data on the last run{failing.length ? <>; not delivering: <b>{failing.map((s) => s.source).join(", ")}</b></> : " - all healthy"}.</p>
      </section>
      <FilterBar fields={[{ kind: "text", name: "q", label: "Source", placeholder: "e.g. sam, ted" }, { kind: "select", name: "state", label: "State", options: facet(allRows, (s) => s.note) }]} values={p} action="/settings" />
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted"><th className="px-4 py-2">Source</th><th className="px-4 py-2">Last run (UTC)</th><th className="px-4 py-2">Open rows</th><th className="px-4 py-2">State</th></tr></thead>
          <tbody>{rows.map((s) => (
            <tr key={s.source} className="border-b border-line/60">
              <td className="px-4 py-2 font-semibold">{s.source}</td>
              <td className="px-4 py-2 whitespace-nowrap">{s.last_run_utc}</td>
              <td className="px-4 py-2 tabular-nums">{num(s.rows).toLocaleString()}</td>
              <td className="px-4 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${s.note === "OK" ? "bg-gobg text-go" : "bg-watchbg text-watch"}`}>{s.note}</span></td>
            </tr>
          ))}</tbody>
        </table>
      </div>
    </div>
  );
}
