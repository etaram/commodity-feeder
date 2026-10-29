import Link from "next/link";
import { getDeals, getIsrael, num, usd, pct, ROUTE_LABEL } from "@/lib/data";
import Decide from "@/components/Decide";

export const revalidate = 900;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-white px-5 py-4 shadow-sm">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-bold text-navy">{value}</div>
    </div>
  );
}

export default async function Today() {
  const [deals, israel] = await Promise.all([getDeals(), getIsrael()]);
  const pursue = deals.filter((d) => d.decision === "Pursue");
  const top = pursue
    .filter((d) => d.days_left === "" || num(d.days_left) >= 5)
    .sort((a, b) => num(b.priority_ev_usd) - num(a.priority_ev_usd))
    .slice(0, 10);
  const ilNew = israel.filter((r) => r.new === "NEW" && r.kind !== "exemption");
  const evTotal = pursue.reduce((s, d) => s + num(d.ev_usd), 0);
  const closing = deals.filter((d) => d.decision === "Pursue" && num(d.days_left) > 0 && num(d.days_left) <= 10).length;

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Deals worth pursuing" value={String(pursue.length)} />
        <Stat label="Expected value on the table" value={usd(evTotal)} />
        <Stat label="Closing within 10 days" value={String(closing)} />
        <Stat label="New Israeli notices" value={String(ilNew.length)} />
      </div>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-bold text-navy">What to act on today</h2>
          <span className="text-xs text-muted">ranked by expected value, weighted by your profile</span>
        </div>
        <div className="mt-3 space-y-3">
          {top.map((d) => (
            <div key={d.id} className="rounded-xl border border-line bg-white p-5 shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-xs text-muted">
                    <span className="rounded bg-paper px-1.5 py-0.5 font-bold">{d.country}</span>
                    <span>{d.sector}</span>
                    {d.route && d.route !== "direct" && (
                      <span className="rounded-full bg-[#E6ECF3] px-2 py-0.5 font-semibold text-blue">{ROUTE_LABEL[d.route] || d.route}</span>
                    )}
                    {num(d.fta_edge_pct) > 0 && (
                      <span className="rounded-full bg-gobg px-2 py-0.5 font-semibold text-go">FTA edge +{(num(d.fta_edge_pct) * 100).toFixed(1)}%</span>
                    )}
                    {num(d.press_count) > 0 && (
                      <span className="rounded-full bg-watchbg px-2 py-0.5 font-semibold text-watch">{d.press_count} press</span>
                    )}
                  </div>
                  <Link href={`/deal/${encodeURIComponent(d.id)}`} className="mt-1 block truncate text-[15px] font-semibold text-ink hover:text-accent">
                    {d.title_en || d.id}
                  </Link>
                  <div className="mt-0.5 truncate text-sm text-muted">{d.buyer}</div>
                </div>
                <Decide id={d.id} title={d.title_en || ""} buyer={d.buyer || ""} country={d.country || ""} />
              </div>
              <div className="mt-3 grid grid-cols-3 gap-3 border-t border-line pt-3 text-sm md:grid-cols-6">
                <div><div className="text-[11px] text-muted">Deal value</div><div className="font-semibold">{usd(num(d.deal_value_usd))}</div></div>
                <div><div className="text-[11px] text-muted">Win prob.</div><div className="font-semibold">{pct(d.p_win_market)}</div></div>
                <div><div className="text-[11px] text-muted">Net margin</div><div className="font-semibold">{pct(d.net_margin_pct, 1)}</div></div>
                <div><div className="text-[11px] text-muted">Expected value</div><div className="font-semibold text-go">{usd(num(d.ev_usd))}</div></div>
                <div><div className="text-[11px] text-muted">Deadline</div><div className="font-semibold">{d.deadline || "-"}{d.days_left !== "" ? ` (${d.days_left}d)` : ""}</div></div>
                <div className="text-right">
                  <Link href={`/deal/${encodeURIComponent(d.id)}`} className="text-sm font-semibold text-accent hover:underline">Open deal file</Link>
                </div>
              </div>
            </div>
          ))}
          {!top.length && <div className="rounded-xl border border-line bg-white p-6 text-sm text-muted">Waiting for the next data refresh.</div>}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-bold text-navy">New in Israel</h2>
        <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
              <th className="px-4 py-2">Body</th><th className="px-4 py-2">Title</th><th className="px-4 py-2">Kind</th><th className="px-4 py-2">Deadline</th><th className="px-4 py-2"></th>
            </tr></thead>
            <tbody>
              {ilNew.slice(0, 12).map((r) => (
                <tr key={r.id} className="border-b border-line/60">
                  <td className="px-4 py-2 whitespace-nowrap">{r.body}</td>
                  <td className="px-4 py-2" dir="rtl" style={{ textAlign: "left" }}>{r.title}</td>
                  <td className="px-4 py-2">{r.kind}</td>
                  <td className="px-4 py-2 whitespace-nowrap">{r.deadline || "-"}</td>
                  <td className="px-4 py-2">{r.link && <a href={r.link} target="_blank" className="font-semibold text-accent hover:underline">Open</a>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
