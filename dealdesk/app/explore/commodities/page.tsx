import { getTrends } from "@/lib/data";

export const revalidate = 900;

const sig = (s: string) =>
  s.startsWith("rising fast") ? "bg-nobg text-no" : s.startsWith("rising") ? "bg-watchbg text-watch"
  : s.startsWith("falling") ? "bg-gobg text-go" : "bg-paper text-muted";

const fmt = (v: string) => {
  const n = parseFloat(v);
  return Number.isFinite(n) ? `${n > 0 ? "+" : ""}${n.toFixed(1)}%` : "-";
};

export default async function Commodities() {
  const rows = (await getTrends()).filter((r) => r.group);
  rows.sort((a, b) => Math.abs(parseFloat(b.chg_3m_pct || "0")) - Math.abs(parseFloat(a.chg_3m_pct || "0")));
  const keys = Object.keys(rows[0] || {});
  const k1 = keys.find((k) => k.includes("1m")) || "chg_1m_pct";
  const k3 = keys.find((k) => k.includes("3m")) || "chg_3m_pct";
  const k12 = keys.find((k) => k.includes("12m")) || "chg_12m_pct";

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-bold text-navy">Commodity price trends</h1>
        <p className="text-sm text-muted">World Bank monthly prices by commodity group. Rising prices tighten margins on long contracts; the deal score already accounts for this.</p>
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-4 py-2">Commodity group</th><th className="px-4 py-2">Signal</th>
            <th className="px-4 py-2">1 month</th><th className="px-4 py-2">3 months</th><th className="px-4 py-2">12 months</th><th className="px-4 py-2">Based on</th>
          </tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.group} className="border-b border-line/60">
                <td className="px-4 py-2 font-semibold">{r.group}</td>
                <td className="px-4 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${sig(r.signal || "")}`}>{r.signal || "-"}</span></td>
                <td className="px-4 py-2 tabular-nums">{fmt(r[k1])}</td>
                <td className="px-4 py-2 font-semibold tabular-nums">{fmt(r[k3])}</td>
                <td className="px-4 py-2 tabular-nums">{fmt(r[k12])}</td>
                <td className="px-4 py-2 text-xs text-muted">{(r.series || "").slice(0, 70)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
