// Entry routes and readiness gates for one deal (skills package, 6 Nov 2026), shared by GET /api/deal and the draft
// submission (a draft is labelled a capability inquiry until the deal reaches ready_for_rfq). DEAL_GATES=off removes them.
import { tenders } from "@/lib/index";
import { routeOptions, routesHe } from "@/lib/routes";
import { GATES, readiness, type Readiness } from "@/lib/dealstate";
import { PARTNER_STATES, type DealRecord } from "@/lib/deal";

export async function dealGates(id: string, records: DealRecord[]) {
  if (process.env.DEAL_GATES === "off") return {};
  const t = (await tenders().catch(() => [])).find((x) => x.id === id);
  const st = records.find((r) => r.kind === "stage")?.data || {};
  const partners = records.filter((r) => r.kind === "party" && r.data.role === "partner").map((r) => String(r.data.partner_state || ""));
  const best = partners.sort((a, b) => PARTNER_STATES.indexOf(b as never) - PARTNER_STATES.indexOf(a as never))[0] || "";
  const access = t ? (t.acc === "set-aside" ? "reserved for local bidders (set-aside)" : t.acc === "intl" ? "international bidding" : "") : "";
  const routes = routeOptions({ country: String(t?.c || st.country || ""), access, title: String(t?.t || st.title || ""), sector: String(t?.s || st.sector || ""),
    value_usd: (t?.v ?? (st.value_usd as number | null)) || null, stage: t?.st || "", partner_state: best });
  return { routes, routes_he: routesHe(routes), readiness: readiness(records, routes) };
}

export const INQUIRY_LABEL = "capability inquiry (qualification), not an RFQ";
/** True only when the deal's readiness has reached ready_for_rfq (or a later gate). Unknown readiness counts as not. */
export const rfqReady = (r?: Readiness | null) => !!r && !!r.reached && GATES.indexOf(r.reached) >= GATES.indexOf("ready_for_rfq");
