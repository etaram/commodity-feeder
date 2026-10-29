import { getTrends } from "@/lib/data";
import FilterBar, { type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;

const sig = (s: string) => s.startsWith("rising fast") ? "bg-nobg text-no" : s.startsWith("rising") ? "bg-watchbg text-watch" : s.startsWith("falling") ? "bg-gobg text-go" : "bg-paper text-muted";
const f = (v: string) => { const n = parseFloat(v); return Number.isFinite(n) ? n : null; };
const fmt = (v: string) => { const n = f(v); return n !== null ? `${n > 0 ? "+" : ""}${n.toFixed(1)}%` : "-"; };

export default async function Commodities({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const all = (await getTrends()).filter((r) => r.group);
  const min3 = Number(p.min3 || 0);
  const rows = all.filter((r) => (!p.signal || (r.signal || "").startsWith(p.signal)) &&
    (!p.q || `${r.group} ${r.series}`.toLowerCase().includes(p.q.toLowerCase())) &&
    (!min3 || Math.abs(f(r.chg_3m_pct) ?? 0) >= min3));
  const key = p.sort === "12m" ? "chg_12m_pct" : p.sort === "1m" ? "chg_1m_pct" : "chg_3m_pct";
  rows.sort((a, b) => Math.abs(f(b[key]) ?? 0) - Math.abs(f(a[key]) ?? 0));
  const up = all.filter((r) => (r.signal || "").startsWith("rising")), down = all.filter((r) => (r.signal || "").startsWith("falling"));
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Group or series", placeholder: "e.g. steel, urea, wheat" },
    { kind: "select", name: "signal", label: "Signal", options: [["rising fast", all.filter((r) => r.signal === "rising fast").length], ["rising", up.length], ["stable", all.filter((r) => r.signal === "stable").length], ["falling", down.length]] },
    { kind: "number", name: "min3", label: "Min 3-month move (%)", placeholder: "e.g. 5" },
  ];

  return (
    <div className="space-y-5">
      <h1 className="text-xl font-bold text-navy">Commodity price trends</h1>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm shadow-sm">
        <span className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</span>
        <p className="mt-1">
          <b>{up.length}</b> commodity groups are rising and <b>{down.length}</b> falling over 3 months.
          {up.length > 0 && <> On long fixed-price contracts in <b>{up.slice(0, 3).map((r) => r.group).join(", ")}</b>, price in an adjustment clause or a shorter validity; the deal score already trims their margin.</>}
          {down.length > 0 && <> Falling groups (<b>{down.slice(0, 3).map((r) => r.group).join(", ")}</b>) give room to bid aggressively.</>}
        </p>
      </section>
      <FilterBar fields={fields} values={p} action="/explore/commodities" sort={p.sort || "3m"} sortOptions={[["3m", "Biggest 3-month move"], ["1m", "Biggest 1-month move"], ["12m", "Biggest 12-month move"]]} />
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted"><th className="px-4 py-2">Commodity group</th><th className="px-4 py-2">Signal</th><th className="px-4 py-2">1 month</th><th className="px-4 py-2">3 months</th><th className="px-4 py-2">12 months</th><th className="px-4 py-2">Based on</th></tr></thead>
          <tbody>{rows.map((r) => (
            <tr key={r.group} className="border-b border-line/60">
              <td className="px-4 py-2 font-semibold">{r.group}</td>
              <td className="px-4 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${sig(r.signal || "")}`}>{r.signal || "-"}</span></td>
              <td className="px-4 py-2 tabular-nums">{fmt(r.chg_1m_pct)}</td>
              <td className="px-4 py-2 font-semibold tabular-nums">{fmt(r.chg_3m_pct)}</td>
              <td className="px-4 py-2 tabular-nums">{fmt(r.chg_12m_pct)}</td>
              <td className="px-4 py-2 text-xs text-muted">{(r.series || "").slice(0, 70)}</td>
            </tr>
          ))}
          {!rows.length && <tr><td colSpan={6} className="px-4 py-8 text-center text-muted">No groups match these filters.</td></tr>}</tbody>
        </table>
      </div>
    </div>
  );
}
