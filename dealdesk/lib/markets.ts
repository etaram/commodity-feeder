import Papa from "papaparse";
import { readRanges } from "@/lib/sheets";
import { logEvent } from "@/lib/log";
import { portfolioLine } from "@/lib/verdict";
import { verdict } from "@/lib/verdict";

const RAW = "https://raw.githubusercontent.com/etaram/commodity-feeder/main/data";
const TRACKER = "1yHBXBVCU3_flqKCQN8HCRYclWyvvX4wXQsQYZtiOaX4";
let memo: { at: number; data: unknown } | null = null;

const n = (v: unknown) => { const x = parseFloat(String(v ?? "").replace(/[$,%\s]/g, "").replace(/,/g, "")); return Number.isFinite(x) ? x : null; };
async function csv(path: string) {
  try {
    const r = await fetch(`${RAW}/${path}`, { cache: "no-store" });
    return r.ok ? (Papa.parse<Record<string, string>>(await r.text(), { header: true, skipEmptyLines: true }).data || []) : [];
  } catch { return []; }
}
async function json(path: string) { try { const r = await fetch(`${RAW}/${path}`, { cache: "no-store" }); return r.ok ? await r.json() : null; } catch { return null; } }

type Chg = Record<string, number | null>;
export async function markets() {
  if (memo && Date.now() - memo.at < 180_000) return memo.data;
  const [pc, trends, deals, press, ptj] = await Promise.all([json("leads/price_changes.json"), csv("leads/price_trends.csv"), csv("leads/deal_calc.csv"), csv("leads/press.csv"), json("leads/price_trends.json")]);
  const pser: { series: string; unit: string; month: string; price: number; chg_1m_pct: number | null; chg_3m_pct: number | null; chg_12m_pct: number | null }[] = ptj?.series || [];
  const byId = new Map<string, { chg: Chg }>((pc?.items || []).map((i: { id: string; chg: Chg }) => [i.id, i]));

  // Live read of the Commodities Tracker (includes the manual prices that only the sheet has). Falls back to the GitHub feed.
  let items: Record<string, unknown>[] = [];
  let sheetAt = "", from = "feed";
  try {
    const g = (await readRanges(TRACKER, ["'Master'!A1:AA2100"]))?.[0] || [];
    for (const r of g.slice(1)) {
      const price = n(r[8]);
      if (!r[0] || price === null) continue;
      const tier = String(r[22] || "").slice(0, 2);
      if ((r[17] || "") > sheetAt) sheetAt = r[17];
      items.push({ id: r[0], cat: r[2], hs: r[3], name: r[4], unit: r[6], price, date: r[11], source: r[12], link: r[13], prev: n(r[15]), pchg: n(r[16]), upd: r[17], status: r[18], tier,
        chg: byId.get(r[0])?.chg || {} });
    }
    if (items.length) from = "sheet";
  } catch (e) { items = []; await logEvent("warn", "markets", "tracker sheet read failed, using the GitHub feed", String(e).slice(0, 300)); }
  if (!items.length) {
    if (from === "feed" && !pc) await logEvent("error", "markets", "no price data from the sheet or the feed");
    items = (pc?.items || []).map((i: Record<string, unknown>) => ({ id: i.id, cat: "", hs: i.hs6, name: i.name, unit: i.unit, price: i.price, date: i.date, source: i.source, link: i.link, prev: null, pchg: null, upd: "", status: "", tier: i.tier, chg: i.chg }));
  }

  const pursueAll = deals.filter((d) => d.decision === "Pursue");
  const pl = portfolioLine(deals);
  const top = pursueAll.filter((d) => d.days_left === "" || Number(d.days_left) >= 5)
    .sort((a, b) => Number(b.priority_ev_usd || 0) - Number(a.priority_ev_usd || 0)).slice(0, 12)
    .map((d) => { const v = verdict(d); return { id: d.id, title: d.title_en, buyer: d.buyer, country: d.country, region: d.region, ev: Number(d.ev_usd || 0), days: d.days_left, route: d.route || "direct", action: v.action, next: v.next, reasons: v.reasons.slice(0, 2), risks: v.risks.slice(0, 2), link: d.link }; });

  const data = {
    from, sheet_updated: sheetAt, feed_finished_utc: pc?.feed_finished_utc || "", changes_utc: pc?.updated_utc || "",
    items, worldbank: pc?.worldbank || [],
    trends: trends.filter((t) => t.group).map((t) => ({ group: t.group, signal: t.signal, m1: n(t.chg_1m_pct), m3: n(t.chg_3m_pct), y1: n(t.chg_12m_pct), basis: t.series || "",
      series: pser.filter((x) => (t.series || "").includes(x.series)).map((x) => ({ name: x.series, unit: x.unit, month: x.month, price: x.price, m1: x.chg_1m_pct, m3: x.chg_3m_pct, y1: x.chg_12m_pct })) })),
    deals: { count: pl.count, ev: pl.ev, urgent: pl.urgent, partner: pl.partner, regions: pl.regions, top },
    press: press.slice(0, 8).map((p) => ({ buyer: p.buyer, country: p.country, date: p.date, headline: p.headline, link: p.link })),
  };
  memo = { at: Date.now(), data };
  return data;
}
