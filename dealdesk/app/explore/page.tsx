import Link from "next/link";
import { getCountries, getSectors, getDeals, num, usd, pct } from "@/lib/data";

export const revalidate = 900;

function Bar({ v, max }: { v: number; max: number }) {
  return <div className="h-2 rounded bg-[#E6ECF3]"><div className="h-2 rounded bg-accent" style={{ width: `${Math.max(2, (v / (max || 1)) * 100)}%` }} /></div>;
}

export default async function Explore() {
  const [countries, sectors, deals] = await Promise.all([getCountries(), getSectors(), getDeals()]);
  const topC = countries.filter((c) => c.country && c.country !== "All").sort((a, b) => num(b.open_notices) - num(a.open_notices)).slice(0, 15);
  const maxC = num(topC[0]?.open_notices);
  const secRows = sectors.filter((s) => s.sector !== "All sectors" && s.region === "All regions").sort((a, b) => num(b.open_notices) - num(a.open_notices)).slice(0, 15);
  const maxS = num(secRows[0]?.open_notices);
  const pursue = deals.filter((d) => d.decision === "Pursue");
  const byRegion = new Map<string, { n: number; ev: number }>();
  for (const d of pursue) {
    const r = byRegion.get(d.region || "Other") || { n: 0, ev: 0 };
    r.n += 1; r.ev += num(d.ev_usd);
    byRegion.set(d.region || "Other", r);
  }

  return (
    <div className="space-y-8">
      <div className="flex items-baseline justify-between">
        <h1 className="text-xl font-bold text-navy">Explore the market</h1>
        <div className="text-xs text-muted">
          Deeper cuts live in the <a className="font-semibold text-accent hover:underline" target="_blank" href="https://docs.google.com/spreadsheets/d/1YSeZ_7GHeSb5RxLk1SmwfWTaFtZOuWbktHLoRlDM83Y">Google Sheet ↗</a>
        </div>
      </div>

      <section className="grid gap-6 md:grid-cols-2">
        <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Open tenders by country</h2>
          <div className="mt-3 space-y-2">
            {topC.map((c) => (
              <div key={c.country} className="grid grid-cols-[52px_1fr_70px] items-center gap-2 text-sm">
                <span className="font-bold">{c.country}</span>
                <Bar v={num(c.open_notices)} max={maxC} />
                <span className="text-right tabular-nums text-muted">{num(c.open_notices).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-line bg-white p-5 shadow-sm">
          <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Open tenders by sector</h2>
          <div className="mt-3 space-y-2">
            {secRows.map((s) => (
              <div key={s.sector} className="grid grid-cols-[1fr_120px_60px] items-center gap-2 text-sm">
                <span className="truncate">{s.sector}</span>
                <Bar v={num(s.open_notices)} max={maxS} />
                <span className="text-right tabular-nums text-muted">{num(s.open_notices).toLocaleString()}</span>
              </div>
            ))}
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Where the pursue-worthy money is</h2>
        <table className="mt-2 w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="py-1.5">Region</th><th className="py-1.5">Deals</th><th className="py-1.5">Expected value</th>
          </tr></thead>
          <tbody>
            {[...byRegion.entries()].sort((a, b) => b[1].ev - a[1].ev).map(([r, v]) => (
              <tr key={r} className="border-b border-line/60">
                <td className="py-1.5">{r}</td><td className="py-1.5">{v.n}</td><td className="py-1.5 font-semibold text-go">{usd(v.ev)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">All pursue deals</h2>
        <div className="mt-2 max-h-[560px] overflow-auto">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white"><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
              <th className="py-1.5 pr-2">Country</th><th className="py-1.5 pr-2">Opportunity</th><th className="py-1.5 pr-2">EV</th><th className="py-1.5 pr-2">Win</th><th className="py-1.5">Deadline</th>
            </tr></thead>
            <tbody>
              {pursue.sort((a, b) => num(b.priority_ev_usd) - num(a.priority_ev_usd)).slice(0, 150).map((d) => (
                <tr key={d.id} className="border-b border-line/60">
                  <td className="py-1.5 pr-2 font-bold">{d.country}</td>
                  <td className="py-1.5 pr-2"><Link href={`/deal/${encodeURIComponent(d.id)}`} className="text-accent hover:underline">{(d.title_en || d.id).slice(0, 95)}</Link></td>
                  <td className="py-1.5 pr-2 font-semibold">{usd(num(d.ev_usd))}</td>
                  <td className="py-1.5 pr-2">{pct(d.p_win_market)}</td>
                  <td className="py-1.5 whitespace-nowrap">{d.deadline || "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
