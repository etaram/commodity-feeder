import { suppliers, facet, words, type Supplier } from "@/lib/index";
import { usd } from "@/lib/data";
import FilterBar, { Pager, type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
const PER = 50;
type SP = Record<string, string | undefined>;

const KIND = (r: Supplier) =>
  r.lg ? "Logistics" : r.epc ? "EPC contractor" : r.td ? "Trader" : r.ty === "works/services" ? "Works / services" : r.ty ? "Manufacturer / supplier" : "";

function apply(all: Supplier[], p: SP) {
  const q = words(p.q || "");
  const minQ = Number(p.minq || 0), minW = Number(p.minwins || 0);
  return all.filter((r) => {
    const hay = `${r.n} ${r.p || ""} ${r.cm || ""} ${r.s || ""} ${r.s2 || ""}`.toLowerCase();
    return (!p.country || r.c === p.country) &&
      (!p.region || r.rg === p.region) &&
      (!p.sector || r.s === p.sector || (r.s2 || "").includes(p.sector)) &&
      (!p.kind || KIND(r) === p.kind) &&
      (!p.tier || r.tr === p.tier) &&
      (!minQ || (r.q || 0) >= minQ) &&
      (!minW || (r.w || 0) >= minW) &&
      (!p.exporters || !!r.x) &&
      (!p.sells || (r.bc || "").split(" ").includes(p.sells)) &&
      (!p.web || !!r.web) &&
      (!q.length || q.every((w) => hay.includes(w)));
  });
}

const SORTS: [string, string][] = [["quality", "Quality score"], ["wins", "Public contracts won"], ["usd", "Value won"], ["recent", "Most recent win"], ["name", "Name"]];
function sortRows(rows: Supplier[], s: string) {
  const f = {
    quality: (a: Supplier, b: Supplier) => (b.q || 0) - (a.q || 0),
    wins: (a: Supplier, b: Supplier) => (b.w || 0) - (a.w || 0),
    usd: (a: Supplier, b: Supplier) => (b.u || 0) - (a.u || 0),
    recent: (a: Supplier, b: Supplier) => (b.lw || "").localeCompare(a.lw || ""),
    name: (a: Supplier, b: Supplier) => a.n.localeCompare(b.n),
  }[s as "quality"] || ((a: Supplier, b: Supplier) => (b.q || 0) - (a.q || 0));
  return rows.sort(f);
}

export default async function SuppliersPage({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const { rows: all, error } = await suppliers();
  if (error && !all.length) {
    return (
      <div className="space-y-4">
        <h1 className="text-xl font-bold text-navy">Supplier search</h1>
        <div className="rounded-xl border border-line bg-white p-6 text-sm text-muted">{error}</div>
      </div>
    );
  }
  const rows = sortRows(apply(all, p), p.sort || "quality");
  const page = Math.max(1, Number(p.page || 1)), pages = Math.ceil(rows.length / PER);
  const shown = rows.slice((page - 1) * PER, page * PER);
  const buyerCountries = facet(all.flatMap((r) => (r.bc || "").split(" ").filter(Boolean).map((c) => ({ c }))), (x) => x.c, 200);
  const exporters = rows.filter((r) => r.x).length, strong = rows.filter((r) => (r.q || 0) >= 75).length;
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Products or name", placeholder: "e.g. HDPE pipe, transformers, urea, Siemens" },
    { kind: "select", name: "country", label: "Supplier country", options: facet(all, (r) => r.c) },
    { kind: "select", name: "region", label: "Region", options: facet(all, (r) => r.rg) },
    { kind: "select", name: "sector", label: "Sector", options: facet(all, (r) => r.s) },
    { kind: "select", name: "kind", label: "Type", options: facet(all, KIND) },
    { kind: "select", name: "tier", label: "Tier", options: facet(all, (r) => r.tr) },
    { kind: "number", name: "minq", label: "Min quality (0-100)", placeholder: "e.g. 60" },
    { kind: "number", name: "minwins", label: "Min contracts won", placeholder: "e.g. 3" },
    { kind: "select", name: "sells", label: "Has sold to country", options: buyerCountries },
    { kind: "check", name: "exporters", label: "Proven exporter" },
    { kind: "check", name: "web", label: "Has a website" },
  ];
  const qs = (pg: number) => "?" + new URLSearchParams({ ...Object.fromEntries(Object.entries(p).filter(([, v]) => v) as [string, string][]), page: String(pg) }).toString();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold text-navy">Supplier search</h1>
        <span className="text-xs text-muted">{all.length.toLocaleString()} suppliers from public award records and research · contact details stay in the private Supplier Universe sheet</span>
      </div>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1"><b>{rows.length.toLocaleString()}</b> suppliers match; <b>{strong.toLocaleString()}</b> are top quality (75+) and <b>{exporters.toLocaleString()}</b> have proven cross-border sales - start RFQs with those. Contacts are in the Supplier Universe sheet or via the panel.</p>
      </section>
      <FilterBar fields={fields} values={p} action="/suppliers" sort={p.sort || "quality"} sortOptions={SORTS} />
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Pager page={page} pages={pages} total={rows.length} href={qs} />
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-3 py-2">Quality</th><th className="px-3 py-2">Supplier</th><th className="px-3 py-2">Country</th><th className="px-3 py-2">Sector / products</th>
            <th className="px-3 py-2 text-right">Wins</th><th className="px-3 py-2 text-right">Value won</th><th className="px-3 py-2">Sold to</th><th className="px-3 py-2"></th>
          </tr></thead>
          <tbody>
            {shown.map((r, i) => (
              <tr key={`${r.n}-${i}`} className="border-b border-line/60 align-top">
                <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${(r.q || 0) >= 75 ? "bg-gobg text-go" : (r.q || 0) >= 50 ? "bg-watchbg text-watch" : "bg-paper text-muted"}`}>{r.q ?? "-"}</span></td>
                <td className="px-3 py-2">
                  <div className="font-semibold">{r.n}</div>
                  <div className="text-xs text-muted">{[KIND(r), r.tr ? `tier ${r.tr}` : "", r.x ? `exporter (${r.x})` : ""].filter(Boolean).join(" · ")}</div>
                </td>
                <td className="px-3 py-2 font-bold">{r.c}</td>
                <td className="px-3 py-2 text-xs"><div className="font-semibold text-ink">{r.s}</div><div className="text-muted">{r.p || r.cm || ""}</div></td>
                <td className="px-3 py-2 text-right tabular-nums">{r.w ?? "-"}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.u ? usd(r.u) : "-"}</td>
                <td className="px-3 py-2 text-xs text-muted">{r.bc || "-"}</td>
                <td className="px-3 py-2">{r.web && <a href={r.web} target="_blank" className="text-xs font-semibold text-accent hover:underline">Website</a>}</td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={8} className="px-3 py-8 text-center text-sm text-muted">No suppliers match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      <Pager page={page} pages={pages} total={rows.length} href={qs} />
    </div>
  );
}
