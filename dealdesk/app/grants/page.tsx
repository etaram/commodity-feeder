import { getGrants, type Row } from "@/lib/data";
import { facet } from "@/lib/index";
import FilterBar, { Pager, type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;
const PER = 60;

const daysTo = (d: string) => (d ? Math.round((new Date(d).getTime() - Date.now()) / 864e5) : null);

function apply(rows: Row[], p: SP) {
  const q = (p.q || "").toLowerCase(), within = Number(p.within || 0);
  return rows.filter((r) => {
    const dd = daysTo(r.closes);
    return (!p.source || r.source === p.source) && (!p.sector || r.sector === p.sector) && (!p.region || r.region === p.region) &&
      (!p.status || r.status === p.status) && (!within || (dd !== null && dd >= 0 && dd <= within)) &&
      (!q || `${r.title} ${r.funder} ${r.program}`.toLowerCase().includes(q));
  });
}

export default async function Grants({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const all = (await getGrants()).filter((r) => r.title);
  const rows = apply(all, p).sort((a, b) => (a.closes || "9999").localeCompare(b.closes || "9999"));
  const page = Math.max(1, Number(p.page || 1)), pages = Math.ceil(rows.length / PER);
  const shown = rows.slice((page - 1) * PER, page * PER);
  const soon = rows.filter((r) => { const d = daysTo(r.closes); return d !== null && d >= 0 && d <= 30; }).length;
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Keywords", placeholder: "e.g. solar, water, Africa, hydrogen" },
    { kind: "select", name: "source", label: "Source", options: facet(all, (r) => r.source) },
    { kind: "select", name: "sector", label: "Sector", options: facet(all, (r) => r.sector) },
    { kind: "select", name: "region", label: "Region", options: facet(all, (r) => r.region) },
    { kind: "select", name: "status", label: "Status", options: facet(all, (r) => r.status) },
    { kind: "number", name: "within", label: "Closes within (days)", placeholder: "e.g. 45" },
  ];
  const qs = (pg: number) => "?" + new URLSearchParams({ ...Object.fromEntries(Object.entries(p).filter(([, v]) => v) as [string, string][]), page: String(pg) }).toString();
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold text-navy">Calls for proposals and incentive programmes</h1>
        <span className="text-xs text-muted">grants.gov, EU Funding &amp; Tenders and Israeli government calls · refreshed every 4 hours</span>
      </div>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm leading-6 shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1"><b>{rows.length.toLocaleString()}</b> open or forthcoming calls match, <b>{soon}</b> close within 30 days. Use them two ways: apply where Sinder or a partner is eligible (EU calls are open to Israeli entities through Horizon Europe association), or sell equipment and supplies to the winners, who must spend the grant on procurement.</p>
        <p className="mt-1 text-xs text-muted">Foreign-investor incentives and export-credit programmes are tracked by the incentives agent in the sheet (Incentives tab), since they need case-by-case reading.</p>
      </section>
      <FilterBar fields={fields} values={p} action="/grants" />
      <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-3 py-2">Closes</th><th className="px-3 py-2">Call</th><th className="px-3 py-2">Funder</th><th className="px-3 py-2">Sector</th><th className="px-3 py-2">Status</th><th className="px-3 py-2"></th>
          </tr></thead>
          <tbody>
            {shown.map((r) => {
              const d = daysTo(r.closes);
              return (
                <tr key={r.id} className="border-b border-line/60 align-top">
                  <td className={`px-3 py-2 whitespace-nowrap ${d !== null && d <= 14 ? "font-semibold text-no" : ""}`}>{r.closes || "open"}{d !== null ? <span className="text-xs text-muted"> ({d}d)</span> : null}</td>
                  <td className="px-3 py-2"><a href={r.link} target="_blank" className="font-semibold text-ink hover:text-accent">{r.title}</a><div className="text-xs text-muted">{r.source}{r.program ? ` · ${r.program}` : ""} · {r.eligibility}</div></td>
                  <td className="px-3 py-2 text-xs">{r.funder}<div className="text-muted">{r.region}</div></td>
                  <td className="px-3 py-2 text-xs text-muted">{r.sector}</td>
                  <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${/open|posted/.test(r.status) ? "bg-gobg text-go" : "bg-watchbg text-watch"}`}>{r.status}</span></td>
                  <td className="px-3 py-2"><a href={r.link} target="_blank" className="text-xs font-semibold text-accent hover:underline">Open call</a></td>
                </tr>
              );
            })}
            {!shown.length && <tr><td colSpan={6} className="px-3 py-8 text-center text-muted">No calls match these filters (or the first collection has not run yet).</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
    </div>
  );
}
