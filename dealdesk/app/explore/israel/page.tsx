import { getIsrael, num, type Row } from "@/lib/data";
import { facet } from "@/lib/index";
import FilterBar, { Pager, type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;
const PER = 60;

function apply(rows: Row[], p: SP) {
  const within = Number(p.within || 0), q = (p.q || "").trim().toLowerCase();
  return rows.filter((r) =>
    (p.kind ? r.kind === p.kind : r.kind !== "exemption") &&
    (!p.type || r.body_type === p.type) && (!p.district || r.district === p.district) &&
    (!p.body || r.body === p.body) && (!p.sector || r.sector === p.sector) &&
    (!p.newonly || r.new === "NEW") &&
    (!within || (r.days_left !== "" && num(r.days_left) >= 0 && num(r.days_left) <= within)) &&
    (!q || `${r.title} ${r.body} ${r.number}`.toLowerCase().includes(q)));
}

const SORTS: [string, string][] = [["new", "Newest first"], ["deadline", "Deadline (soonest)"], ["body", "Publisher A-Z"]];

export default async function IsraelPage({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const all = (await getIsrael()).filter((r) => r.id);
  const rows = apply(all, p);
  const s = p.sort || "new";
  rows.sort(s === "deadline" ? (a, b) => (a.deadline || "9999").localeCompare(b.deadline || "9999")
    : s === "body" ? (a, b) => (a.body || "").localeCompare(b.body || "", "he")
    : (a, b) => (b.first_seen || "").localeCompare(a.first_seen || "") || (a.deadline || "9999").localeCompare(b.deadline || "9999"));
  const page = Math.max(1, Number(p.page || 1)), pages = Math.ceil(rows.length / PER);
  const shown = rows.slice((page - 1) * PER, page * PER);
  const closing7 = rows.filter((r) => r.days_left !== "" && num(r.days_left) >= 0 && num(r.days_left) <= 7).length;
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Keywords (Hebrew or number)", placeholder: "e.g. צנרת, תאורה, 12/2026" },
    { kind: "select", name: "kind", label: "Kind", options: facet(all, (r) => r.kind), all: "Tenders and calls" },
    { kind: "select", name: "type", label: "Type of body", options: facet(all, (r) => r.body_type) },
    { kind: "select", name: "district", label: "District", options: facet(all, (r) => r.district) },
    { kind: "select", name: "body", label: "Publisher", options: facet(all, (r) => r.body) },
    { kind: "select", name: "sector", label: "Sector", options: facet(all, (r) => r.sector) },
    { kind: "number", name: "within", label: "Closes within (days)", placeholder: "e.g. 14" },
    { kind: "check", name: "newonly", label: "New (48h) only" },
  ];
  const qs = (pg: number) => "?" + new URLSearchParams({ ...Object.fromEntries(Object.entries(p).filter(([, v]) => v) as [string, string][]), page: String(pg) }).toString();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold text-navy">Israel - public notices</h1>
        <span className="text-xs text-muted">{all.length.toLocaleString()} open notices from {new Set(all.map((r) => r.body)).size} public bodies, scanned daily</span>
      </div>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1"><b>{rows.length}</b> notices match{closing7 ? <>, <b className="text-no">{closing7}</b> close within 7 days</> : null}. Goods and equipment tenders from municipalities and government companies are the ones Sinder can supply; local services (cleaning, guarding, consulting) are usually not worth it.</p>
      </section>
      <FilterBar fields={fields} values={p} action="/explore/israel" sort={s} sortOptions={SORTS} />
      <div className="flex items-center justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-4 py-2">New</th><th className="px-4 py-2">Body</th><th className="px-4 py-2">Type</th>
            <th className="px-4 py-2">Title</th><th className="px-4 py-2">Kind</th><th className="px-4 py-2">Deadline</th><th className="px-4 py-2">Days</th><th className="px-4 py-2"></th>
          </tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="border-b border-line/60">
                <td className="px-4 py-2">{r.new === "NEW" && <span className="rounded bg-gobg px-1.5 py-0.5 text-[10px] font-bold text-go">NEW</span>}</td>
                <td className="px-4 py-2 whitespace-nowrap">{r.body}</td>
                <td className="px-4 py-2 whitespace-nowrap text-muted">{r.body_type}</td>
                <td className="px-4 py-2" dir="rtl" style={{ textAlign: "left" }}>{r.title}</td>
                <td className="px-4 py-2">{r.kind}</td>
                <td className="px-4 py-2 whitespace-nowrap">{r.deadline || "-"}</td>
                <td className={`px-4 py-2 font-semibold ${num(r.days_left) > 0 && num(r.days_left) <= 7 ? "text-no" : ""}`}>{r.days_left || "-"}</td>
                <td className="px-4 py-2">{r.link && <a href={r.link} target="_blank" className="font-semibold text-accent hover:underline">Open</a>}</td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={8} className="px-4 py-8 text-center text-muted">No notices match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
    </div>
  );
}
