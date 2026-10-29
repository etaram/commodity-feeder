import Link from "next/link";
import { getDeals, getIsrael, num, usd, pct, ROUTE_LABEL, type Row } from "@/lib/data";
import { facet } from "@/lib/index";
import { verdict, portfolioLine } from "@/lib/verdict";
import Decide from "@/components/Decide";
import FilterBar, { type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
type SP = Record<string, string | undefined>;

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-line bg-white px-5 py-4 shadow-sm">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">{label}</div>
      <div className="mt-1 text-2xl font-bold text-navy">{value}</div>
    </div>
  );
}

function apply(rows: Row[], p: SP) {
  const minEv = Number(p.minev || 0) * 1000, within = Number(p.within || 0);
  return rows.filter((d) =>
    (!p.region || d.region === p.region) && (!p.country || d.country === p.country) && (!p.sector || d.sector === p.sector) &&
    (!p.route || (d.route || "direct") === p.route) && (!minEv || num(d.ev_usd) >= minEv) &&
    (!within || (d.days_left !== "" && num(d.days_left) >= 0 && num(d.days_left) <= within)) &&
    (!p.fta || num(d.fta_edge_pct) > 0) && (!p.q || `${d.title_en} ${d.buyer}`.toLowerCase().includes(p.q.toLowerCase())));
}

export default async function Today({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const [deals, israel] = await Promise.all([getDeals(), getIsrael()]);
  const pursueAll = deals.filter((d) => d.decision === "Pursue");
  const pursue = apply(pursueAll, p);
  const top = pursue.filter((d) => d.days_left === "" || num(d.days_left) >= 5).sort((a, b) => num(b.priority_ev_usd) - num(a.priority_ev_usd)).slice(0, Number(p.n || 10));
  const ilNew = israel.filter((r) => r.new === "NEW" && r.kind !== "exemption");
  const pl = portfolioLine(pursue);
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Keywords", placeholder: "e.g. pipes, transformers, Mekorot" },
    { kind: "select", name: "region", label: "Region", options: facet(pursueAll, (d) => d.region) },
    { kind: "select", name: "country", label: "Country", options: facet(pursueAll, (d) => d.country) },
    { kind: "select", name: "sector", label: "Sector", options: facet(pursueAll, (d) => d.sector) },
    { kind: "select", name: "route", label: "Route", options: facet(pursueAll, (d) => d.route || "direct") },
    { kind: "number", name: "minev", label: "Min expected value ($K)", placeholder: "e.g. 50" },
    { kind: "number", name: "within", label: "Closes within (days)", placeholder: "e.g. 21" },
    { kind: "check", name: "fta", label: "Has trade-agreement edge" },
  ];
  const t1 = top[0], v1 = t1 ? verdict(t1) : null;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Deals worth pursuing" value={String(pl.count)} />
        <Stat label="Expected value on the table" value={usd(pl.ev)} />
        <Stat label="Closing within 10 days" value={String(pl.urgent)} />
        <Stat label="New Israeli notices" value={String(ilNew.length)} />
      </div>

      <section className="rounded-xl border-l-4 border-go bg-white p-5 shadow-sm">
        <div className="text-[11px] font-bold uppercase tracking-wide text-muted">Bottom line</div>
        {pl.count ? (
          <div className="mt-2 space-y-2 text-[15px] leading-7">
            <p>
              <b>{pl.count} deals</b> are worth pursuing{Object.values(p).some(Boolean) ? " in this view" : ""}, together <b>{usd(pl.ev)}</b> in expected profit.
              {pl.regions.length > 0 && <> The money sits mostly in <b>{pl.regions.map(([r, v]) => `${r} (${usd(v)})`).join(", ")}</b>.</>}
            </p>
            {t1 && v1 && (
              <p>
                Start with <Link href={`/deal/${encodeURIComponent(t1.id)}`} className="font-semibold text-accent hover:underline">{(t1.title_en || t1.id).slice(0, 90)}</Link> ({t1.country}): <b>{v1.action.toLowerCase()}</b>, expected value {usd(num(t1.ev_usd))}. {v1.next}
              </p>
            )}
            <p className="text-sm text-muted">
              {pl.urgent > 0 ? `${pl.urgent} of them close within 10 days - decide on those first. ` : ""}
              {pl.partner > 0 ? `${pl.partner} need a local partner. ` : ""}
              {ilNew.length > 0 ? `${ilNew.length} new Israeli notices since yesterday.` : ""}
            </p>
          </div>
        ) : <p className="mt-2 text-sm text-muted">No pursue-worthy deal matches these filters.</p>}
      </section>

      <FilterBar fields={fields} values={p} action="/today" sort={p.n || "10"} sortOptions={[["10", "Show 10"], ["25", "Show 25"], ["50", "Show 50"]]} sortName="n" sortLabel="How many" />

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-bold text-navy">What to act on</h2>
          <span className="text-xs text-muted">ranked by expected value, weighted by your profile</span>
        </div>
        <div className="mt-3 space-y-3">
          {top.map((d) => {
            const v = verdict(d);
            return (
              <div key={d.id} className="rounded-xl border border-line bg-white p-5 shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span className="rounded bg-paper px-1.5 py-0.5 font-bold">{d.country}</span>
                      <span>{d.sector}</span>
                      {d.route && d.route !== "direct" && (<span className="rounded-full bg-[#E6ECF3] px-2 py-0.5 font-semibold text-blue">{ROUTE_LABEL[d.route] || d.route}</span>)}
                      {num(d.fta_edge_pct) > 0 && (<span className="rounded-full bg-gobg px-2 py-0.5 font-semibold text-go">FTA edge +{(num(d.fta_edge_pct) * 100).toFixed(1)}%</span>)}
                      {num(d.press_count) > 0 && (<span className="rounded-full bg-watchbg px-2 py-0.5 font-semibold text-watch">{d.press_count} press</span>)}
                    </div>
                    <Link href={`/deal/${encodeURIComponent(d.id)}`} className="mt-1 block truncate text-[15px] font-semibold text-ink hover:text-accent">{d.title_en || d.id}</Link>
                    <div className="mt-0.5 truncate text-sm text-muted">{d.buyer}</div>
                  </div>
                  <Decide id={d.id} title={d.title_en || ""} buyer={d.buyer || ""} country={d.country || ""} />
                </div>
                <div className="mt-3 rounded-lg bg-paper px-3 py-2 text-sm"><b className="text-go">{v.action}.</b> {v.next}</div>
                <div className="mt-3 grid grid-cols-3 gap-3 border-t border-line pt-3 text-sm md:grid-cols-6">
                  <div><div className="text-[11px] text-muted">Deal value</div><div className="font-semibold">{usd(num(d.deal_value_usd))}</div></div>
                  <div><div className="text-[11px] text-muted">Win prob.</div><div className="font-semibold">{pct(d.p_win_market)}</div></div>
                  <div><div className="text-[11px] text-muted">Net margin</div><div className="font-semibold">{pct(d.net_margin_pct, 1)}</div></div>
                  <div><div className="text-[11px] text-muted">Expected value</div><div className="font-semibold text-go">{usd(num(d.ev_usd))}</div></div>
                  <div><div className="text-[11px] text-muted">Deadline</div><div className="font-semibold">{d.deadline || "-"}{d.days_left !== "" ? ` (${d.days_left}d)` : ""}</div></div>
                  <div className="text-right"><Link href={`/deal/${encodeURIComponent(d.id)}`} className="text-sm font-semibold text-accent hover:underline">Open deal file</Link></div>
                </div>
              </div>
            );
          })}
          {!top.length && <div className="rounded-xl border border-line bg-white p-6 text-sm text-muted">No deals match these filters.</div>}
        </div>
      </section>

      <section>
        <div className="flex items-baseline justify-between">
          <h2 className="text-lg font-bold text-navy">New in Israel</h2>
          <Link href="/explore/israel" className="text-sm font-semibold text-accent hover:underline">All Israeli notices</Link>
        </div>
        <div className="mt-3 overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted"><th className="px-4 py-2">Body</th><th className="px-4 py-2">Title</th><th className="px-4 py-2">Kind</th><th className="px-4 py-2">Deadline</th><th className="px-4 py-2"></th></tr></thead>
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
