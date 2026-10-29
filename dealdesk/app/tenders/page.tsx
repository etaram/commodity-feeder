import Link from "next/link";
import { tenders, facet, words, type Tender } from "@/lib/index";
import { usd } from "@/lib/data";
import FilterBar, { Pager, type Field } from "@/components/FilterBar";

export const dynamic = "force-dynamic";
const PER = 50;

type SP = Record<string, string | undefined>;

const SIZES: [string, number][] = [["Under $100K", 0], ["$100K - $1M", 0], ["$1M - $10M", 0], ["$10M - $50M", 0], ["Over $50M", 0]];
const inSize = (v: number | null, s: string) => {
  if (v == null) return false;
  if (s === "Under $100K") return v < 1e5;
  if (s === "$100K - $1M") return v >= 1e5 && v < 1e6;
  if (s === "$1M - $10M") return v >= 1e6 && v < 1e7;
  if (s === "$10M - $50M") return v >= 1e7 && v < 5e7;
  if (s === "Over $50M") return v >= 5e7;
  return true;
};

function apply(all: Tender[], p: SP) {
  const q = words(p.q || "");
  const minV = Number(p.min || 0) * 1000, maxV = Number(p.max || 0) * 1000;
  const within = Number(p.within || 0), minDays = Number(p.mindays || 0);
  return all.filter((r) =>
    (!p.country || r.c === p.country) &&
    (!p.region || r.rg === p.region) &&
    (!p.sector || r.s === p.sector) &&
    (!p.group || r.g === p.group) &&
    (!p.decision || r.d === p.decision) &&
    (!p.source || r.src === p.source) &&
    (!p.stage || r.st === p.stage) &&
    (!p.size || inSize(r.v, p.size)) &&
    (!minV || (r.v ?? -1) >= minV) &&
    (!maxV || (r.v != null && r.v <= maxV)) &&
    (!p.valued || r.v != null) &&
    (!p.nosetaside || r.acc !== "set-aside") &&
    (!p.newonly || r.n === 1) &&
    (!within || (r.dd != null && r.dd >= 0 && r.dd <= within)) &&
    (!minDays || (r.dd != null && r.dd >= minDays)) &&
    (!q.length || q.every((w) => (r.t + " " + r.b + " " + r.id).toLowerCase().includes(w))),
  );
}

const SORTS: [string, string][] = [["ev", "Expected value"], ["value", "Tender value"], ["deadline", "Deadline (soonest)"], ["score", "Fit score"], ["new", "Newest first"]];

function sortRows(rows: Tender[], s: string) {
  const by = {
    ev: (a: Tender, b: Tender) => (b.ev ?? -1e12) - (a.ev ?? -1e12),
    value: (a: Tender, b: Tender) => (b.v ?? -1) - (a.v ?? -1),
    deadline: (a: Tender, b: Tender) => (a.dd ?? 9999) - (b.dd ?? 9999),
    score: (a: Tender, b: Tender) => (b.sc ?? 0) - (a.sc ?? 0),
    new: (a: Tender, b: Tender) => b.n - a.n || (b.sc ?? 0) - (a.sc ?? 0),
  }[s as "ev"] || ((a: Tender, b: Tender) => (b.ev ?? -1e12) - (a.ev ?? -1e12));
  return rows.sort(by);
}

const chip = (d: string) => d === "Pursue" ? "bg-gobg text-go" : d === "Watch" ? "bg-watchbg text-watch" : "bg-paper text-muted";

export default async function TendersPage({ searchParams }: { searchParams: Promise<SP> }) {
  const p = await searchParams;
  const all = await tenders();
  const rows = sortRows(apply(all, p), p.sort || "ev");
  const page = Math.max(1, Number(p.page || 1)), pages = Math.ceil(rows.length / PER);
  const shown = rows.slice((page - 1) * PER, page * PER);
  const valueSum = rows.reduce((s, r) => s + (r.v || 0), 0);
  const fields: Field[] = [
    { kind: "text", name: "q", label: "Keywords", placeholder: "e.g. cable, pipes, solar, Mekorot" },
    { kind: "select", name: "country", label: "Country", options: facet(all, (r) => r.c) },
    { kind: "select", name: "region", label: "Region", options: facet(all, (r) => r.rg) },
    { kind: "select", name: "sector", label: "Sector", options: facet(all, (r) => r.s) },
    { kind: "select", name: "group", label: "Commodity group", options: facet(all, (r) => r.g) },
    { kind: "select", name: "size", label: "Tender size", options: SIZES.map(([l]) => [l, all.filter((r) => inSize(r.v, l)).length] as [string, number]), all: "Any size" },
    { kind: "number", name: "min", label: "Min value ($K)", placeholder: "e.g. 500" },
    { kind: "number", name: "max", label: "Max value ($K)" },
    { kind: "number", name: "within", label: "Closes within (days)", placeholder: "e.g. 30" },
    { kind: "number", name: "mindays", label: "At least days left", placeholder: "e.g. 10" },
    { kind: "select", name: "decision", label: "Engine decision", options: facet(all, (r) => r.d) },
    { kind: "select", name: "stage", label: "Stage", options: facet(all, (r) => r.st) },
    { kind: "select", name: "source", label: "Source", options: facet(all, (r) => r.src) },
    { kind: "check", name: "valued", label: "Has a stated value" },
    { kind: "check", name: "nosetaside", label: "Hide US set-asides" },
    { kind: "check", name: "newonly", label: "New (48h) only" },
  ];
  const qs = (pg: number) => "?" + new URLSearchParams({ ...Object.fromEntries(Object.entries(p).filter(([, v]) => v) as [string, string][]), page: String(pg) }).toString();

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h1 className="text-xl font-bold text-navy">Tender search</h1>
        <span className="text-xs text-muted">{all.length.toLocaleString()} open notices from every source · the link keeps your filters, so you can send it to a partner</span>
      </div>
      <FilterBar fields={fields} values={p} action="/tenders" sort={p.sort || "ev"} sortOptions={SORTS} />
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="text-sm"><b>{rows.length.toLocaleString()}</b> tenders match · stated value <b>{usd(valueSum)}</b> · <b>{rows.filter((r) => r.d === "Pursue").length}</b> Pursue</div>
        <Pager page={page} pages={pages} total={rows.length} href={qs} />
      </div>
      <div className="overflow-x-auto rounded-xl border border-line bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
            <th className="px-3 py-2">Country</th><th className="px-3 py-2">Tender</th><th className="px-3 py-2">Sector</th>
            <th className="px-3 py-2 text-right">Value</th><th className="px-3 py-2">Deadline</th><th className="px-3 py-2">Decision</th><th className="px-3 py-2 text-right">EV</th><th className="px-3 py-2"></th>
          </tr></thead>
          <tbody>
            {shown.map((r) => (
              <tr key={r.id} className="border-b border-line/60 align-top">
                <td className="px-3 py-2 font-bold">{r.c}{r.n ? <span className="ml-1 rounded bg-gobg px-1 text-[9px] text-go">NEW</span> : null}</td>
                <td className="px-3 py-2">
                  {r.d === "Pursue" || r.d === "Watch"
                    ? <Link href={`/deal/${encodeURIComponent(r.id)}`} className="font-semibold text-ink hover:text-accent">{r.t || r.id}</Link>
                    : <span className="font-semibold">{r.t || r.id}</span>}
                  <div className="text-xs text-muted">{r.b}{r.acc === "set-aside" ? " · US small-business set-aside" : ""}{r.st === "planned" ? " · planned" : ""}</div>
                </td>
                <td className="px-3 py-2 text-xs text-muted">{r.s}</td>
                <td className="px-3 py-2 text-right tabular-nums">{r.v != null ? usd(r.v) : "-"}</td>
                <td className={`px-3 py-2 whitespace-nowrap ${r.dd != null && r.dd >= 0 && r.dd <= 7 ? "font-semibold text-no" : ""}`}>{r.dl || "-"}{r.dd != null ? <span className="text-xs text-muted"> ({r.dd}d)</span> : null}</td>
                <td className="px-3 py-2"><span className={`rounded-full px-2 py-0.5 text-xs font-bold ${chip(r.d)}`}>{r.d || "-"}</span></td>
                <td className="px-3 py-2 text-right tabular-nums">{r.ev != null && r.ev > 0 ? usd(r.ev) : "-"}</td>
                <td className="px-3 py-2">{r.l && <a href={r.l} target="_blank" className="text-xs font-semibold text-accent hover:underline">Notice</a>}</td>
              </tr>
            ))}
            {!shown.length && <tr><td colSpan={8} className="px-3 py-8 text-center text-sm text-muted">No tenders match these filters.</td></tr>}
          </tbody>
        </table>
      </div>
      <Pager page={page} pages={pages} total={rows.length} href={qs} />
    </div>
  );
}
