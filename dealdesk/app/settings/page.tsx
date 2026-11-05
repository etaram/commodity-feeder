import { getSourceQuality, getSources, num } from "@/lib/data";
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
  const quality = (await getSourceQuality().catch(() => [])).filter((q) => q.source);
  const flagged = quality.filter((q) => q.flags);
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
        <p className="mt-1"><b>{allRows.length - failing.length}</b> of <b>{allRows.length}</b> sources delivered data on the last run{failing.length ? <>; not delivering: <b>{failing.map((s) => s.source).join(", ")}</b></> : " - all delivered"}. Delivery is not quality: see below.</p>
      </section>
      <section className="rounded-xl border-l-4 border-watch bg-white p-4 text-sm shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Data quality (separate from delivery)</span>
        <p className="mt-1">A source that ran is not proof that its notices are fresh, complete or unique. <b>{flagged.length}</b> of <b>{quality.length}</b> notice sources have a quality flag: thin parse (deadline or buyer under half), duplicates, notices past their deadline (now kept out of the open list), or nothing new.</p>
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead><tr className="border-b border-line text-left uppercase text-muted"><th className="px-2 py-1">Source</th><th className="px-2 py-1">Open</th><th className="px-2 py-1">New</th><th className="px-2 py-1">Deadline</th><th className="px-2 py-1">Value</th><th className="px-2 py-1">Buyer</th><th className="px-2 py-1">Duplicates</th><th className="px-2 py-1">Mirrored</th><th className="px-2 py-1">Useful to Sinder</th><th className="px-2 py-1">Flags</th></tr></thead>
            <tbody>{quality.slice(0, 80).map((q) => (
              <tr key={q.source} className="border-b border-line/60">
                <td className="px-2 py-1 font-semibold">{q.source}</td><td className="px-2 py-1 tabular-nums">{num(q.open).toLocaleString()}</td>
                <td className="px-2 py-1 tabular-nums">{q.fresh_7d}%</td><td className="px-2 py-1 tabular-nums">{q.deadline}%</td><td className="px-2 py-1 tabular-nums">{q.value}%</td>
                <td className="px-2 py-1 tabular-nums">{q.buyer}%</td><td className="px-2 py-1 tabular-nums">{q.dup_in}%</td><td className="px-2 py-1 tabular-nums">{q.mirrored}%</td>
                <td className="px-2 py-1 tabular-nums">{q.goods}%</td><td className="px-2 py-1 text-watch">{q.flags}</td>
              </tr>))}</tbody>
          </table>
        </div>
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
