import { getGovernance, num, type Row } from "@/lib/data";
import { facet } from "@/lib/index";
import FilterBar, { type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;

const chip = (f: string) => f === "open" ? "bg-gobg text-go" : f === "caution" ? "bg-watchbg text-watch" : "bg-nobg text-no";
const g = (v: string) => (v === "" ? "-" : num(v).toFixed(2));
const pct = (v: string) => (v === "" ? "-" : `${Math.round(num(v) * 100)}%`);

export default async function Integrity({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const all = (await getGovernance()).filter((r) => r.country);
  const q = (p.q || "").toUpperCase();
  const rows = all.filter((r: Row) => (!p.flag || r.flag === p.flag) && (!q || r.country.includes(q)))
    .sort((a, b) => (p.sort === "low" ? num(a.integrity_score) - num(b.integrity_score) : num(b.integrity_score) - num(a.integrity_score)));
  const n = (f: string) => all.filter((r) => r.flag === f).length;
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Country code", placeholder: "e.g. KEN, IND, BRA" },
    { kind: "select", name: "flag", label: "Verdict", options: facet(all, (r) => r.flag) },
  ];
  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-navy">Regulation and integrity advisor</h1>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm leading-6 shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1"><b>{n("open")}</b> markets are open (bid on the merits), <b>{n("caution")}</b> need verification before spending, and <b>{n("high risk")}</b> are high risk: few firms bid there, awards repeat to the same suppliers, and a cold bid rarely wins on price alone.</p>
        <p className="mt-1">How to read it: talking to the procurement office before a tender (questions, market consultation, presenting capabilities) is lawful and normal; do it in writing. Paying or doing favours for officials is not an option anywhere: it is a crime under Israeli Penal Law 291A, the US FCPA and the UK Bribery Act. Where a market seems to require it, the advice is to decline, or to enter only through a vetted local partner under written anti-bribery terms.</p>
        <p className="mt-1 text-xs text-muted">Score 0-100: half from the World Bank Worldwide Governance Indicators (control of corruption, rule of law), half from what our award records show (bidders per tender, share won by a single bidder, share won by foreign firms). Each tender also gets its own note (incumbent, very short deadline) on its deal file.</p>
      </section>
      <FilterBar fields={fields} values={p} action="/integrity" sort={p.sort || "high"} sortOptions={[["high", "Most open first"], ["low", "Highest risk first"]]} />
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-3 py-2">Country</th><th className="px-3 py-2">Score</th><th className="px-3 py-2">Verdict</th>
            <th className="px-3 py-2 text-right">Control of corruption</th><th className="px-3 py-2 text-right">Rule of law</th>
            <th className="px-3 py-2 text-right">Median bidders</th><th className="px-3 py-2 text-right">Single-bid share</th><th className="px-3 py-2 text-right">Foreign wins</th><th className="px-3 py-2">Basis</th>
          </tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.country} className="border-b border-line/60" title={r.advice}>
              <td className="px-3 py-2 font-bold"><a href={`/tenders?country=${r.country}`} className="hover:text-accent">{r.country}</a></td>
              <td className="px-3 py-2 tabular-nums font-semibold">{r.integrity_score}</td>
              <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${chip(r.flag)}`}>{r.flag}</span></td>
              <td className="px-3 py-2 text-right tabular-nums">{g(r.control_of_corruption)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{g(r.rule_of_law)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{r.median_bidders || "-"}</td>
              <td className="px-3 py-2 text-right tabular-nums">{pct(r.single_bid_share)}</td>
              <td className="px-3 py-2 text-right tabular-nums">{pct(r.foreign_win_rate)}</td>
              <td className="px-3 py-2 text-xs text-muted">{r.basis}</td>
            </tr>))}
            {!rows.length && <tr><td colSpan={9} className="px-3 py-8 text-center text-muted">No countries match (or the first calculation has not run yet).</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
