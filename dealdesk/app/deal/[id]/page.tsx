import Link from "next/link";
import { getDeal, getPress, getAwards, getGovernance, num, usd, pct, ROUTE_LABEL, type Row } from "@/lib/data";
import Decide from "@/components/Decide";
import JobButton from "@/components/JobButton";
import ContactFinder from "@/components/ContactFinder";
import BottomLine from "@/components/BottomLine";
import { verdict } from "@/lib/verdict";
import { tenders, isClosed } from "@/lib/index";

export const revalidate = 900;

function liveDays(deadline: string): number | null {
  const d = Date.parse(String(deadline).slice(0, 10));
  if (!isFinite(d)) return null;
  const n = new Date();
  return Math.round((d - Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate())) / 86400000);
}
function shareText(d: Row): string {
  const v = num(d.est_value_usd);
  return [
    `*${d.title_en || d.title_original || "Tender"}*`,
    `${d.buyer || ""} · ${d.country || ""}${d.sector ? " · " + d.sector : ""}`,
    v ? `Value: ${usd(v)}` : "",
    d.deadline ? `Deadline: ${d.deadline}` : "",
    d.decision ? `Sinder view: ${d.decision}` : "",
    d.link ? `Official notice: ${d.link}` : "",
    `Deal file: https://sinder-deal-desk.vercel.app/deal/${encodeURIComponent(d.id)}`,
  ].filter(Boolean).join("\n");
}

const IG_CHIP: Record<string, string> = { open: "bg-gobg text-go", caution: "bg-watchbg text-watch", "high risk": "bg-nobg text-no" };

function Advisor({ flag, score, note, gov }: { flag?: string; score?: string; note?: string; gov?: Row }) {
  const f = flag || gov?.flag || "";
  return (
    <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Regulation and integrity advisor</h2>
        {f ? <span className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${IG_CHIP[f] || "bg-paper text-muted"}`}>{f}{score || gov?.integrity_score ? ` · ${score || gov?.integrity_score}/100` : ""}</span> : null}
      </div>
      {f ? (
        <>
          <p className="mt-2 text-sm leading-6">{note || gov?.advice}</p>
          {gov && <div className="mt-2 grid grid-cols-2 gap-x-6 gap-y-1 text-xs text-muted md:grid-cols-4">
            <div>Control of corruption: <b className="text-ink">{gov.control_of_corruption || "-"}</b></div>
            <div>Rule of law: <b className="text-ink">{gov.rule_of_law || "-"}</b></div>
            <div>Single-bid share: <b className="text-ink">{gov.single_bid_share ? `${Math.round(num(gov.single_bid_share) * 100)}%` : "-"}</b></div>
            <div>Foreign wins: <b className="text-ink">{gov.foreign_win_rate ? `${Math.round(num(gov.foreign_win_rate) * 100)}%` : "-"}</b></div>
          </div>}
          <p className="mt-2 text-xs text-muted">Early, documented contact with the procurement office is lawful and recommended. Payments or favours to officials are never an option (Israeli Penal Law 291A, US FCPA, UK Bribery Act). <a href="/integrity" className="font-semibold text-accent hover:underline">All countries</a></p>
        </>
      ) : <p className="mt-2 text-sm text-muted">No governance or award data for this country yet.</p>}
    </section>
  );
}

function Fact({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-lg border border-line bg-white px-4 py-3">
      <div className="text-[11px] font-bold uppercase tracking-wide text-muted">{label}</div>
      <div className={`mt-0.5 ${strong ? "text-xl font-bold text-navy" : "text-sm font-semibold"}`}>{value}</div>
    </div>
  );
}

export default async function DealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [deal, govAll] = await Promise.all([getDeal(decodeURIComponent(id)), getGovernance()]);
  if (!deal) {
    const t = (await tenders()).find((r) => r.id === decodeURIComponent(id));
    const gv = t ? govAll.find((g) => g.country === t.c) : undefined;
    return (
      <div className="space-y-4">
        <div className="flex items-center gap-2 text-xs text-muted"><Link href="/tenders" className="font-semibold text-accent hover:underline">Tenders</Link><span>/</span><span>{decodeURIComponent(id)}</span></div>
        {t ? (
          <div className="rounded-xl border border-line bg-white p-6 shadow-sm">
            <h1 className="text-lg font-bold text-navy">{t.t || t.id}</h1>
            <div className="mt-1 text-sm text-muted">{t.b} &middot; {t.c} &middot; {t.s}</div>
            <div className="mt-3 text-sm">Value: <b>{t.v != null ? usd(t.v) : "not stated"}</b> &middot; Deadline: <b>{t.dl || "-"}</b> &middot; Engine decision: <b>{t.d}</b></div>
            <p className="mt-3 text-sm text-muted">This notice is outside the top 8,000 deals, so it has no full deal file. Open the official notice for the details.</p>
            {t.l && <a href={t.l} target="_blank" className="mt-3 inline-block rounded-full bg-accent px-3 py-1 text-xs font-bold text-white">Open the official notice</a>}
          </div>
        ) : null}
        {t ? (
          <Advisor gov={gv} />
        ) : (
          <div className="rounded-xl border border-line bg-white p-8 text-sm text-muted">This notice has closed or is no longer in the data. <Link href="/tenders" className="text-accent font-semibold">Back to search</Link></div>
        )}
      </div>
    );
  }
  const [pressAll, awardsAll] = await Promise.all([getPress(), getAwards()]);
  const press = pressAll.filter((p) => p.id === deal.id);
  const buyerKey = (deal.buyer || "").toLowerCase().slice(0, 25);
  const history = buyerKey ? awardsAll.filter((a) => (a.buyer || "").toLowerCase().includes(buyerKey)).slice(0, 8) : [];

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 text-xs text-muted">
          <Link href="/today" className="font-semibold text-accent hover:underline">Today</Link><span>/</span><span>{deal.id}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
          <h1 className="max-w-3xl text-xl font-bold text-navy">{deal.title_en || deal.id}</h1>
          <Decide id={deal.id} title={deal.title_en || ""} buyer={deal.buyer || ""} country={deal.country || ""} />
        </div>
        <div className="mt-1 text-sm text-muted">{deal.buyer} · {deal.country} · {deal.sector}{deal.commodity ? ` · ${deal.commodity}` : ""}</div>
        <div className="mt-2 flex flex-wrap gap-2 text-xs">
          <span className={`rounded-full px-2.5 py-1 font-bold ${deal.decision === "Pursue" ? "bg-gobg text-go" : deal.decision === "Watch" ? "bg-watchbg text-watch" : "bg-paper text-muted"}`}>{deal.decision}</span>
          <span className="rounded-full bg-[#E6ECF3] px-2.5 py-1 font-semibold text-blue">{ROUTE_LABEL[deal.route] || deal.route || "direct"}</span>
          {deal.deadline && <span className="rounded-full bg-paper px-2.5 py-1 font-semibold">Deadline {deal.deadline} ({liveDays(deal.deadline) ?? "?"} days)</span>}
          {deal.link && <a href={deal.link} target="_blank" className="rounded-full bg-accent px-2.5 py-1 font-bold text-white hover:bg-blue">Open the official notice</a>}
          <a href={"https://wa.me/?text=" + encodeURIComponent(shareText(deal))} target="_blank" rel="noopener" className="rounded-full bg-[#1F7A4D] px-2.5 py-1 font-bold text-white hover:opacity-90">Share on WhatsApp</a>
        </div>
      </div>
      {isClosed(deal.deadline) && <div className="rounded-xl border-l-4 border-no bg-nobg p-3 text-sm font-semibold text-no">This tender closed on {deal.deadline}. It is kept here for reference only and no longer appears in the lists.</div>}

      <BottomLine v={verdict(deal)} />

      <Advisor flag={deal.integrity_flag} score={deal.integrity_score} note={deal.integrity_note} gov={govAll.find((g) => g.country === deal.country)} />

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Fact label="Expected value" value={usd(num(deal.ev_usd))} strong />
        <Fact label="Deal value" value={`${usd(num(deal.deal_value_usd))} (${deal.value_basis || "estimated"})`} />
        <Fact label="Win probability" value={`${pct(deal.p_win_market)} vs ~${deal.est_bidders || "?"} bidders`} />
        <Fact label="Net margin" value={`${pct(deal.net_margin_pct, 1)} (gross ${pct(deal.gross_margin_pct, 1)})`} />
      </div>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">How the numbers were built</h2>
        <p className="mt-2 text-sm leading-6">{deal.why || "No explanation recorded."}</p>
        <div className="mt-3 grid grid-cols-2 gap-x-6 gap-y-1 text-sm md:grid-cols-3">
          <div>Addressable share: <b>{pct(deal.addressable_share)}</b></div>
          <div>Value confidence: <b>{pct(deal.value_confidence)}</b></div>
          <div>Pursuit cost: <b>{usd(num(deal.pursuit_cost_usd))}</b></div>
          <div>Payment terms: <b>{deal.payment_days || "?"} days</b></div>
          <div>Price trend (3m): <b>{deal.price_trend_3m_pct ? `${deal.price_trend_3m_pct}%` : "-"} {deal.price_signal}</b></div>
          <div>ROI: <b>{deal.roi ? `${num(deal.roi).toFixed(1)}x` : "-"}</b></div>
        </div>
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Trade-agreement edge</h2>
        {deal.fta_note ? (
          <p className="mt-2 text-sm leading-6">{deal.fta_note}{deal.import_duty_pct ? ` Import duty for this commodity group: ${pct(deal.import_duty_pct, 1)}.` : ""}</p>
        ) : (<p className="mt-2 text-sm text-muted">No duty data for this market and group yet, or the scope is works or services.</p>)}
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Buyer in the news (last 120 days)</h2>
          {num(deal.press_count) > 0 && <span className="text-xs text-muted">{deal.press_count} articles</span>}
        </div>
        {press.length ? (
          <ul className="mt-2 space-y-2">
            {press.map((p, i) => (
              <li key={i} className="text-sm">
                <a href={p.link} target="_blank" className="font-semibold text-accent hover:underline">{p.headline}</a>
                <span className="ml-2 text-xs text-muted">{p.domain} · {p.date}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-sm text-muted">No linked press coverage found for this buyer.</p>
        )}
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">This buyer&apos;s recent awards</h2>
        {history.length ? (
          <table className="mt-2 w-full text-sm">
            <thead><tr className="border-b border-line text-left text-[11px] uppercase text-muted">
              <th className="py-1.5 pr-3">Date</th><th className="py-1.5 pr-3">What</th><th className="py-1.5 pr-3">Winner</th><th className="py-1.5">Value</th>
            </tr></thead>
            <tbody>{history.map((a, i) => (
              <tr key={i} className="border-b border-line/60">
                <td className="py-1.5 pr-3 whitespace-nowrap">{a.published || "-"}</td>
                <td className="py-1.5 pr-3">{(a.title || "").slice(0, 90)}</td>
                <td className="py-1.5 pr-3">{(a.winners || a.winner || "-").slice(0, 60)}</td>
                <td className="py-1.5 whitespace-nowrap">{a.value_usd ? usd(num(a.value_usd)) : a.value ? usd(num(a.value)) : "-"}</td>
              </tr>
            ))}</tbody>
          </table>
        ) : (
          <p className="mt-2 text-sm text-muted">No award history for this buyer in the last 12 months of collected awards.</p>
        )}
      </section>

      <section className="rounded-xl border border-line bg-white p-5 shadow-sm">
        <h2 className="text-sm font-bold uppercase tracking-wide text-muted">Hand it to the research agents</h2>
        <p className="mt-1 text-xs text-muted">Queues a job for the worker agent; results appear in the sheet (Panel Jobs).</p>
        <div className="mt-3 flex flex-wrap gap-2">
          <JobButton type="eligibility" deal={deal} label="Full eligibility check" />
          <JobButton type="quote" deal={deal} label="Build a price quote" />
          <JobButton type="logistics" deal={deal} label="Logistics plan" />
          <JobButton type="supplier_search" deal={deal} label="Find suppliers" />
          <ContactFinder deal={deal} />
        </div>
      </section>
    </div>
  );
}
