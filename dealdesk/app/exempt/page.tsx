import { getExempt, getIlExempt, num, usd, type Row } from "@/lib/data";
import { facet } from "@/lib/index";
import FilterBar, { Pager, type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;
const PER = 50;
const ILS = 0.27; // display conversion ILS -> USD, approximate

export default async function Exempt({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const view = p.view === "contracts" ? "contracts" : "notices";
  const [notices, contracts] = await Promise.all([getExempt(), getIlExempt()]);
  const q = (p.q || "").toLowerCase();
  const page = Math.max(1, Number(p.page || 1));
  const qs = (pg: number) => "?" + new URLSearchParams({ ...Object.fromEntries(Object.entries(p).filter(([, v]) => v) as [string, string][]), page: String(pg) }).toString();

  if (view === "contracts") {
    const rows = contracts.filter((r) => (!p.window || r.renewal_window === p.window) && (!p.office || r.office === p.office) &&
      (!q || `${r.title} ${r.supplier} ${r.office} ${r.unit}`.toLowerCase().includes(q)) && (!p.min || num(r.amount) * ILS >= Number(p.min) * 1000));
    const pages = Math.ceil(rows.length / PER), shown = rows.slice((page - 1) * PER, page * PER);
    const soon = contracts.filter((r) => r.renewal_window === "next 6 months");
    const fields: Field[] = [
      { kind: "text", name: "q", label: "Keywords (Hebrew)", placeholder: "e.g. ציוד, תחזוקה, מחשוב" },
      { kind: "select", name: "window", label: "Contract ends", options: facet(contracts, (r) => r.renewal_window) },
      { kind: "select", name: "office", label: "Ministry / body", options: facet(contracts, (r) => r.office) },
      { kind: "number", name: "min", label: "Min value ($K)", placeholder: "e.g. 100" },
    ];
    return (
      <div className="space-y-5">
        <Header view={view} />
        <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm leading-6 shadow-sm">
          <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
          <p className="mt-1"><b>{contracts.length.toLocaleString()}</b> Israeli government contracts were signed without a tender and are still running. <b>{soon.length.toLocaleString()}</b> end within 6 months ({usd(soon.reduce((s, r) => s + num(r.amount) * ILS, 0))}): each one must be renewed or re-procured, which is the moment to offer the ministry an alternative supplier or ask it to publish an open tender.</p>
          <p className="mt-1 text-xs text-muted">Source: Government Procurement Administration, data.gov.il. The publisher updates this report irregularly, so check the publication date on each row; amounts are in shekels.</p>
        </section>
        <FilterBar fields={fields} values={p} action="/exempt" hidden={{ view: "contracts" }} />
        <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
        <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
              <th className="px-3 py-2">Ends</th><th className="px-3 py-2">Contract</th><th className="px-3 py-2">Supplier today</th><th className="px-3 py-2 text-right">Value (ILS)</th><th className="px-3 py-2">Exemption clause</th>
            </tr></thead>
            <tbody>{shown.map((r, i) => (
              <tr key={i} className="border-b border-line/60 align-top">
                <td className="px-3 py-2 whitespace-nowrap">{r.end}<div className={`text-xs ${r.renewal_window === "next 6 months" ? "font-semibold text-no" : "text-muted"}`}>{r.renewal_window}</div></td>
                <td className="px-3 py-2" dir="rtl" style={{ textAlign: "left" }}><div className="font-semibold">{r.title}</div><div className="text-xs text-muted">{r.office} · {r.unit}</div></td>
                <td className="px-3 py-2 text-xs" dir="rtl" style={{ textAlign: "left" }}>{r.supplier || "-"}</td>
                <td className="px-3 py-2 text-right tabular-nums">{num(r.amount).toLocaleString()}</td>
                <td className="px-3 py-2 text-xs text-muted" dir="rtl" style={{ textAlign: "left" }}>{r.clause}</td>
              </tr>))}
              {!shown.length && <tr><td colSpan={5} className="px-3 py-8 text-center text-muted">No contracts match (or the first collection has not run yet).</td></tr>}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
      </div>
    );
  }

  const rows = notices.filter((r) => (!p.country || r.country === p.country) && (!p.sector || r.sector === p.sector) &&
    (!q || `${r.title_en} ${r.buyer}`.toLowerCase().includes(q)));
  const pages = Math.ceil(rows.length / PER), shown = rows.slice((page - 1) * PER, page * PER);
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Keywords", placeholder: "e.g. maintenance, software, vehicles" },
    { kind: "select", name: "country", label: "Country", options: facet(notices, (r) => r.country) },
    { kind: "select", name: "sector", label: "Sector", options: facet(notices, (r) => r.sector) },
  ];
  return (
    <div className="space-y-5">
      <Header view={view} />
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm leading-6 shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1"><b>{notices.length.toLocaleString()}</b> open notices of purchases without an open tender (exemptions, direct awards, quotations). There is no bid to submit, but each one shows a buyer that is buying now: contact it directly, and where the law gives a window to object (Israeli exemption notices), a capable alternative supplier can ask for a competition.</p>
      </section>
      <FilterBar fields={fields} values={p} action="/exempt" />
      <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-3 py-2">Country</th><th className="px-3 py-2">Purchase</th><th className="px-3 py-2">Type</th><th className="px-3 py-2 text-right">Value</th><th className="px-3 py-2">Published</th><th className="px-3 py-2"></th>
          </tr></thead>
          <tbody>{shown.map((r) => (
            <tr key={r.id} className="border-b border-line/60 align-top">
              <td className="px-3 py-2 font-bold">{r.country}</td>
              <td className="px-3 py-2"><a href={`/deal/${encodeURIComponent(r.id)}`} className="font-semibold text-ink hover:text-accent">{r.title_en}</a><div className="text-xs text-muted">{r.buyer} · {r.sector}</div></td>
              <td className="px-3 py-2 text-xs text-muted">{r.notice_type}</td>
              <td className="px-3 py-2 text-right tabular-nums">{num(r.est_value_usd) ? usd(num(r.est_value_usd)) : "-"}</td>
              <td className="px-3 py-2 whitespace-nowrap text-xs">{r.published || "-"}</td>
              <td className="px-3 py-2">{r.link && <a href={r.link} target="_blank" className="text-xs font-semibold text-accent hover:underline">Notice</a>}</td>
            </tr>))}
            {!shown.length && <tr><td colSpan={6} className="px-3 py-8 text-center text-muted">No notices match (or the first collection has not run yet).</td></tr>}
          </tbody>
        </table>
      </div>
      <div className="flex justify-end"><Pager page={page} pages={pages} total={rows.length} href={qs} /></div>
    </div>
  );
}

function Header({ view }: { view: string }) {
  const tab = (v: string, label: string) => (
    <a href={v === "notices" ? "/exempt" : "/exempt?view=contracts"} className={`rounded-full px-3 py-1 text-sm font-semibold ${view === v ? "bg-navy text-white" : "bg-white text-ink border border-line hover:border-accent"}`}>{label}</a>
  );
  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h1 className="text-xl font-bold text-navy">Purchases without a tender</h1>
      <div className="flex gap-2">{tab("notices", "Live exemption and direct-award notices")}{tab("contracts", "Israeli exemption contracts (renewals)")}</div>
    </div>
  );
}
