import Link from "next/link";
import { usd } from "@/lib/data";
import { tenders, facet, type Tender } from "@/lib/index";
import FilterBar, { type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;

function Bar({ v, max, tone = "bg-accent" }: { v: number; max: number; tone?: string }) {
  return <div className="h-2 rounded bg-[#E6ECF3]"><div className={`h-2 rounded ${tone}`} style={{ width: `${Math.max(2, (v / (max || 1)) * 100)}%` }} /></div>;
}

function group(rows: Tender[], key: (r: Tender) => string) {
  const m = new Map<string, { n: number; pursue: number; ev: number; value: number }>();
  for (const r of rows) {
    const k = key(r) || "Other";
    const x = m.get(k) || { n: 0, pursue: 0, ev: 0, value: 0 };
    x.n += 1; x.value += r.v || 0;
    if (r.d === "Pursue") { x.pursue += 1; x.ev += Math.max(0, r.ev || 0); }
    m.set(k, x);
  }
  return [...m.entries()];
}

export default async function Explore({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const all = await tenders();
  const rows = all.filter((r) => (!p.region || r.rg === p.region) && (!p.sector || r.s === p.sector) && (!p.country || r.c === p.country) &&
    (!p.stage || r.st === p.stage) && (!p.nosetaside || r.acc !== "set-aside"));
  const measure = p.by === "ev" ? "ev" : p.by === "value" ? "value" : "n";
  const val = (x: { n: number; ev: number; value: number }) => measure === "ev" ? x.ev : measure === "value" ? x.value : x.n;
  const fmt = (x: { n: number; ev: number; value: number }) => measure === "n" ? x.n.toLocaleString() : usd(val(x));
  const byC = group(rows, (r) => r.c).sort((a, b) => val(b[1]) - val(a[1])).slice(0, 20);
  const byS = group(rows, (r) => r.s).sort((a, b) => val(b[1]) - val(a[1])).slice(0, 20);
  const byR = group(rows, (r) => r.rg).sort((a, b) => b[1].ev - a[1].ev);
  const maxC = byC.length ? val(byC[0][1]) : 1, maxS = byS.length ? val(byS[0][1]) : 1;
  const total = group(rows, () => "all")[0]?.[1] || { n: 0, pursue: 0, ev: 0, value: 0 };
  const topR = byR[0], topS = group(rows.filter((r) => r.d === "Pursue"), (r) => r.s).sort((a, b) => b[1].ev - a[1].ev)[0];
  const qs = (extra: Record<string, string>) => "/tenders?" + new URLSearchParams({ ...Object.fromEntries(Object.entries({ region: p.region, sector: p.sector, country: p.country }).filter(([, v]) => v) as [string, string][]), ...extra }).toString();
  const fields: Field[] = [
    { kind: "select", name: "region", label: "Region", options: facet(all, (r) => r.rg) },
    { kind: "select", name: "country", label: "Country", options: facet(all, (r) => r.c) },
    { kind: "select", name: "sector", label: "Sector", options: facet(all, (r) => r.s) },
    { kind: "select", name: "stage", label: "Stage", options: facet(all, (r) => r.st) },
    { kind: "check", name: "nosetaside", label: "Hide US set-asides" },
  ];

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-bold text-navy">Explore the market</h1>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-[15px] leading-7 shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1">
          <b>{total.n.toLocaleString()}</b> open tenders in this view, <b>{total.pursue}</b> worth pursuing (expected value <b>{usd(total.ev)}</b>).
          {topR && topR[1].ev > 0 && <> The best region is <b>{topR[0]}</b> ({usd(topR[1].ev)} from {topR[1].pursue} deals)</>}
          {topS && topS[1].ev > 0 && <>, the best sector <b>{topS[0]}</b> ({usd(topS[1].ev)})</>}.
          {" "}Volume alone is misleading: Europe has the most tenders, but the money per deal is often higher where competition is thinner.
        </p>
      </section>
      <FilterBar fields={fields} values={p} action="/explore" sort={measure === "n" ? "n" : measure} sortName="by" sortLabel="Rank by" sortOptions={[["n", "Number of tenders"], ["ev", "Expected value (Pursue)"], ["value", "Stated value"]]} />

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold uppercase tracking-wide text-muted">By country</h2>
          <div className="mt-3 space-y-2">{byC.map(([c, x]) => (
            <Link key={c} href={qs({ country: c })} className="grid grid-cols-[52px_1fr_80px] items-center gap-2 text-sm hover:text-accent">
              <span className="font-bold">{c}</span><Bar v={val(x)} max={maxC} tone={measure === "ev" ? "bg-go" : "bg-accent"} /><span className="text-right tabular-nums text-muted">{fmt(x)}</span>
            </Link>))}</div>
        </div>
        <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold uppercase tracking-wide text-muted">By sector</h2>
          <div className="mt-3 space-y-2">{byS.map(([s, x]) => (
            <Link key={s} href={qs({ sector: s })} className="grid grid-cols-[1fr_110px_80px] items-center gap-2 text-sm hover:text-accent">
              <span className="truncate">{s}</span><Bar v={val(x)} max={maxS} tone={measure === "ev" ? "bg-go" : "bg-accent"} /><span className="text-right tabular-nums text-muted">{fmt(x)}</span>
            </Link>))}</div>
        </div>
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">By region</h2>
        <table className="mt-2 w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted"><th className="py-1.5">Region</th><th className="py-1.5 text-right">Open tenders</th><th className="py-1.5 text-right">Pursue</th><th className="py-1.5 text-right">Expected value</th><th className="py-1.5 text-right">Stated value</th></tr></thead>
          <tbody>{byR.map(([r, x]) => (
            <tr key={r} className="border-b border-line/60">
              <td className="py-1.5"><Link href={qs({ region: r, decision: "Pursue" })} className="hover:text-accent">{r}</Link></td>
              <td className="py-1.5 text-right tabular-nums">{x.n.toLocaleString()}</td><td className="py-1.5 text-right tabular-nums">{x.pursue}</td>
              <td className="py-1.5 text-right font-semibold text-go tabular-nums">{usd(x.ev)}</td><td className="py-1.5 text-right tabular-nums text-muted">{usd(x.value)}</td>
            </tr>))}</tbody>
        </table>
      </section>
    </div>
  );
}
