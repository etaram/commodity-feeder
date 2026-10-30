import { getPriceChanges } from "@/lib/data";
import PricesTable from "@/components/PricesTable";

export const dynamic = "force-dynamic";

const il = (iso: string) => {
  if (!iso) return "unknown";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "unknown" : new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Jerusalem", day: "2-digit", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(d) + " (Israel time)";
};

export default async function Prices() {
  const d = await getPriceChanges();
  if (!d) return <div className="rounded-xl border border-line bg-white p-6 text-sm">Price data is not available right now. Try again in a few minutes.</div>;
  const live = d.items.filter((i) => i.tier !== "T4");
  const withChg = live.filter((i) => i.chg.d1 !== null).length;
  const yahoo = live.filter((i) => i.chg_src.startsWith("Yahoo")).length;
  const movers = live.filter((i) => i.chg.d1 !== null).sort((a, b) => Math.abs(b.chg.d1 ?? 0) - Math.abs(a.chg.d1 ?? 0)).slice(0, 5);
  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-2">
        <h1 className="text-xl font-bold text-navy">Commodity prices</h1>
        <div className="text-right text-xs text-muted">
          <div>Last price update: <b className="text-ink">{il(d.feed_finished_utc)}</b></div>
          <div>Changes recalculated: {il(d.updated_utc)}</div>
        </div>
      </div>
      <section className="rounded-xl border-l-4 border-go bg-white p-4 text-sm shadow-sm">
        <p><b>{d.count.toLocaleString("en-US")}</b> commodities tracked: <b>{live.length}</b> live market prices (exchanges, market reports) and <b>{(d.count - live.length).toLocaleString("en-US")}</b> trade-statistics unit values that update monthly.</p>
        <p className="mt-1 text-muted">Prices are collected twice a day (about 07:40 and 23:10 Israel time). Exchange prices are delayed quotes. Red means the price went up (costlier to buy), green means down.</p>
        {movers.length > 0 && <p className="mt-2"><b>Biggest 1-day moves:</b> {movers.map((m) => `${m.name.split(" - ")[0]} ${(m.chg.d1 ?? 0) > 0 ? "+" : ""}${(m.chg.d1 ?? 0).toFixed(1)}%`).join("; ")}.</p>}
        <p className="mt-2 text-xs text-muted">Change columns: {yahoo} exchange prices show every horizon straight away (Yahoo daily history). For the rest, 1-day to 12-month changes appear as our own price history builds up ({withChg} live prices have at least a 1-day change today). A dash means not enough history yet. The World Bank tab gives 1, 3 and 12 month changes for {d.worldbank.length} core commodities.</p>
      </section>
      <PricesTable items={d.items} wb={d.worldbank} />
    </div>
  );
}
