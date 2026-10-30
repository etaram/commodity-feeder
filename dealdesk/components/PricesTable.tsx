"use client";
import { useMemo, useState } from "react";
import type { PriceItem, PriceData } from "@/lib/data";

const H: [string, string][] = [["d1", "1 day"], ["d7", "7 days"], ["m1", "1 month"], ["m3", "3 months"], ["y1", "12 months"]];
const chip = (v: number | null | undefined) => {
  if (v === null || v === undefined) return <span className="text-muted">-</span>;
  const cls = v > 0.05 ? "text-no" : v < -0.05 ? "text-go" : "text-muted";
  return <span className={`font-semibold tabular-nums ${cls}`}>{v > 0 ? "+" : ""}{v.toFixed(Math.abs(v) < 10 ? 1 : 0)}%</span>;
};
const price = (p: number) => (p >= 100 ? p.toFixed(1) : p >= 1 ? p.toFixed(2) : p.toPrecision(3));

export default function PricesTable({ items, wb }: { items: PriceItem[]; wb: PriceData["worldbank"] }) {
  const [view, setView] = useState<"live" | "trade" | "wb">("live");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState("name");
  const [limit, setLimit] = useState(150);
  const live = useMemo(() => items.filter((i) => i.tier !== "T4"), [items]);
  const trade = useMemo(() => items.filter((i) => i.tier === "T4"), [items]);
  const base = view === "live" ? live : trade;
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    const r = base.filter((i) => !s || `${i.name} ${i.hs6} ${i.source}`.toLowerCase().includes(s));
    if (sort !== "name") r.sort((a, b) => Math.abs(b.chg[sort] ?? -1) - Math.abs(a.chg[sort] ?? -1));
    else r.sort((a, b) => a.name.localeCompare(b.name));
    return r;
  }, [base, q, sort]);
  const wbRows = useMemo(() => wb.filter((i) => !q.trim() || `${i.group} ${i.name}`.toLowerCase().includes(q.trim().toLowerCase())), [wb, q]);
  const tab = (k: typeof view, label: string) => (
    <button onClick={() => { setView(k); setLimit(150); }} className={`rounded-full border px-3 py-1 text-sm font-semibold ${view === k ? "border-navy bg-navy text-white" : "border-line bg-white text-navy"}`}>{label}</button>
  );
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        {tab("live", `Live market prices (${live.length})`)}
        {tab("trade", `Trade-statistics unit values (${trade.length})`)}
        {tab("wb", `World Bank monthly (${wb.length})`)}
      </div>
      <div className="flex flex-wrap gap-2">
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search commodity, HS code or source..." className="min-w-[220px] flex-1 rounded-lg border border-line bg-white px-3 py-2 text-sm" />
        {view !== "wb" && (
          <select value={sort} onChange={(e) => setSort(e.target.value)} className="rounded-lg border border-line bg-white px-3 py-2 text-sm">
            <option value="name">Sort: name</option>
            {H.map(([k, l]) => (<option key={k} value={k}>Sort: biggest {l} move</option>))}
          </select>
        )}
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        {view === "wb" ? (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted"><th className="px-3 py-2">Commodity</th><th className="px-3 py-2">Group</th><th className="px-3 py-2">Price</th><th className="px-3 py-2">Month</th><th className="px-3 py-2">1 month</th><th className="px-3 py-2">3 months</th><th className="px-3 py-2">12 months</th></tr></thead>
            <tbody>{wbRows.map((i) => (
              <tr key={i.name} className="border-b border-line/60"><td className="px-3 py-2 font-semibold">{i.name}</td><td className="px-3 py-2 text-xs text-muted">{i.group}</td>
                <td className="px-3 py-2 tabular-nums">{i.price} <span className="text-xs text-muted">{i.unit}</span></td><td className="px-3 py-2 text-xs text-muted">{i.month}</td>
                <td className="px-3 py-2">{chip(i.chg.m1)}</td><td className="px-3 py-2">{chip(i.chg.m3)}</td><td className="px-3 py-2">{chip(i.chg.y1)}</td></tr>
            ))}</tbody>
          </table>
        ) : (
          <table className="w-full text-sm">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted"><th className="px-3 py-2">Commodity</th><th className="px-3 py-2">Price (USD)</th><th className="px-3 py-2">Price date</th>{H.map(([k, l]) => (<th key={k} className="px-3 py-2">{l}</th>))}<th className="px-3 py-2">Source</th></tr></thead>
            <tbody>{rows.slice(0, limit).map((i) => (
              <tr key={i.id} className="border-b border-line/60">
                <td className="px-3 py-2 font-semibold">{i.name}<div className="text-[11px] font-normal text-muted">HS {i.hs6}</div></td>
                <td className="px-3 py-2 tabular-nums">{price(i.price)} <span className="text-xs text-muted">{i.unit}</span></td>
                <td className="px-3 py-2 text-xs text-muted">{i.date}</td>
                {H.map(([k]) => (<td key={k} className="px-3 py-2">{chip(i.chg[k])}</td>))}
                <td className="px-3 py-2 text-xs">{i.link ? <a href={i.link} target="_blank" rel="noreferrer" className="text-navy underline">{i.source.slice(0, 38)}</a> : i.source.slice(0, 38)}</td>
              </tr>
            ))}
            {!rows.length && <tr><td colSpan={9} className="px-4 py-8 text-center text-muted">Nothing matches.</td></tr>}</tbody>
          </table>
        )}
      </div>
      {view !== "wb" && rows.length > limit && (<button onClick={() => setLimit(limit + 300)} className="rounded-lg border border-line bg-white px-4 py-2 text-sm font-semibold text-navy">Show more ({rows.length - limit} left)</button>)}
    </div>
  );
}
