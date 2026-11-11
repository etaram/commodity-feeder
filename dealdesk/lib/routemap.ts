// Maps one deal file (lib/deal.ts records) to one OpportunityRoute for lib/route.ts. Pure: no I/O, no clock (the
// caller passes `now`), no model. The rule of this file: a value the deal file does not contain stays null or
// "unknown". Nothing is estimated, converted or filled with a default number. Each mapping decision is listed in
// docs/release-2026-11-13/DECISION_ENGINE.md ("Wired").
import type { DealRecord } from "@/lib/deal";
import type { Compared } from "@/lib/quotes";
import { decideSend } from "@/lib/mandate";
import { evaluateRoute, priority, type DemandStatus, type Evaluation, type EvidenceItem, type NextTask, type OpportunityRoute, type Priority, type Requirement, type TechnicalFit } from "@/lib/route";

export type QuoteComparison = { groups: { basis: string; rows: Compared[] }[] } | null;
/** What the caller knows outside the deal records. tender: the notice with the deal's id in the tender index, if any. */
export type DealContext = { deal_id?: string; workspace?: string; tender?: { stage: string; deadline: string; buyer: string; title: string; link: string } | null };

// The note lib/dealagent.ts writes on a party record after the owner approved one outgoing message. The deal API
// never lets a caller set a record's note, so this value is only ever written by that approval step.
export const OWNER_APPROVED_NOTE = "approved by the owner";
// Legal checks are recorded as requirements with these names (status met needs evidence, as for any requirement).
export const LEGAL_ITEMS = { data_rights: "Legal: data rights", representation: "Legal: representation" } as const;
const LEGAL_RE = { data_rights: /^legal\s*[:\-]\s*data rights\b/i, representation: /^legal\s*[:\-]\s*representation\b/i };

const s = (v: unknown) => String(v ?? "").trim();
const key = (v: unknown) => s(v).toLowerCase();
const n = (v: unknown): number | null => (typeof v === "number" && Number.isFinite(v) ? v : null);
const date = (v: unknown): string | null => (/^\d{4}-\d{2}-\d{2}$/.test(s(v)) ? s(v) : null);

function live(records: DealRecord[]): DealRecord[] {
  const latest = new Map<string, DealRecord>();
  for (const r of records) { const k = `${r.kind}|${r.record_id}`, p = latest.get(k); if (!p || r.version >= p.version) latest.set(k, r); }
  return [...latest.values()].filter((r) => r.status !== "deleted");
}

export type SupplierChoice = { supplier: string | null; basis: "selected party" | "only quote" | "only supplier party" | "several candidates, none selected" | "none recorded" };
/** One route carries one supplier. A selected party wins; otherwise a supplier is taken only when there is exactly one. */
export function chooseSupplier(records: DealRecord[]): SupplierChoice {
  const r = live(records);
  const parties = r.filter((x) => x.kind === "party" && x.data.role === "supplier" && s(x.data.status || x.status) !== "dropped");
  const names = (xs: unknown[]) => { const m = new Map<string, string>(); for (const x of xs) if (key(x) && !m.has(key(x))) m.set(key(x), s(x)); return [...m.values()]; };
  const selected = names(parties.filter((p) => s(p.data.status || p.status) === "selected").map((p) => p.data.name));
  if (selected.length === 1) return { supplier: selected[0], basis: "selected party" };
  if (selected.length > 1) return { supplier: null, basis: "several candidates, none selected" };
  const quoting = names(r.filter((x) => x.kind === "quote").map((q) => q.data.supplier));
  if (quoting.length === 1) return { supplier: quoting[0], basis: "only quote" };
  if (quoting.length > 1) return { supplier: null, basis: "several candidates, none selected" };
  const all = names(parties.map((p) => p.data.name));
  if (all.length === 1) return { supplier: all[0], basis: "only supplier party" };
  return { supplier: null, basis: all.length ? "several candidates, none selected" : "none recorded" };
}

const TENDER_STAGE: Record<string, DemandStatus> = { planned: "planned", tender: "open", open: "open", awarded: "awarded", closed: "closed", cancelled: "cancelled" };
function host(link: string): string { try { return new URL(link).hostname.toLowerCase().replace(/^www\./, ""); } catch { return ""; } }

export function routeFromDeal(records: DealRecord[], comparison: QuoteComparison, now: string, ctx: DealContext = {}): OpportunityRoute {
  const r = live(records);
  const dealId = s(ctx.deal_id) || s(r[0]?.deal_id);
  const stage = r.find((x) => x.kind === "stage")?.data || {};
  const econ = r.find((x) => x.kind === "economics")?.data || null;
  const reqs = r.filter((x) => x.kind === "requirement");
  const parties = r.filter((x) => x.kind === "party");
  const tender = ctx.tender || null;

  // ---- supply: one supplier, its latest quote, the requirement checklist ----
  const { supplier } = chooseSupplier(records);
  const quoteRec = supplier ? r.filter((x) => x.kind === "quote" && key(x.data.supplier) === key(supplier)).sort((a, b) => (a.time < b.time ? 1 : a.time > b.time ? -1 : 0))[0] || null : null;
  const quote = quoteRec?.data || null;
  const compared = supplier && comparison ? comparison.groups.flatMap((g) => g.rows).filter((x) => key(x.supplier) === key(supplier)) : [];
  const priced = !!quote && n(quote.unit_price) !== null && !(compared.length && compared.every((x) => x.flags.includes("no price")));

  const legal = (re: RegExp): boolean | null => {
    const hit = reqs.filter((x) => re.test(s(x.data.item))).map((x) => s(x.data.status || x.status));
    return hit.includes("not_met") ? false : hit.includes("met") ? true : null;
  };
  const technical = reqs.filter((x) => !LEGAL_RE.data_rights.test(s(x.data.item)) && !LEGAL_RE.representation.test(s(x.data.item)));
  const requirements: Requirement[] = technical.map((x) => {
    const st = s(x.data.status || x.status);
    return { name: s(x.data.item), mandatory: x.data.mandatory !== false, status: st === "met" ? "verified" : st === "not_met" ? "contradicted" : "unknown" };
  });
  // The deal file has no supplier-match verdict. The only fit it can state is the checklist: every mandatory
  // requirement recorded as met (each needs its evidence to be saved as met) reads as "supported"; anything less
  // is "unknown". A not-met mandatory requirement is reported by the engine as a contradicted requirement.
  const mandatory = requirements.filter((x) => x.mandatory);
  const technical_fit: TechnicalFit = supplier && mandatory.length && mandatory.every((x) => x.status === "verified") ? "supported" : "unknown";

  // ---- demand ----
  const buyer = s(parties.find((p) => p.data.role === "buyer" && s(p.data.status || p.status) !== "dropped")?.data.name) || s(tender?.buyer);
  const stageName = s(stage.stage);
  const status: DemandStatus = tender ? TENDER_STAGE[key(tender.stage)] || "unknown" : stageName === "won" ? "awarded" : stageName === "lost" ? "closed" : "unknown";

  // ---- evidence: only what the file can name a source for ----
  const evidence: EvidenceItem[] = [];
  if (tender && s(tender.link)) evidence.push({ claim: "the demand is published", source_family: host(tender.link) || "tender-notice", status: "official-source-asserted", retrieved_at: null, valid_until: null });
  if (quoteRec && supplier && s(quote?.source_ref)) evidence.push({ claim: `quote from ${supplier}`, source_family: `supplier:${key(supplier)}`,
    status: quote?.availability === "confirmed" ? "counterparty-confirmed" : "client-asserted", retrieved_at: s(quoteRec.time).slice(0, 10) || null, valid_until: date(quote?.valid_until) });

  // ---- economics: stated absolute amounts only; percentage items (duty, bank, financing, commission) are not applied ----
  const goods = econ ? n(econ.cost_goods) : null;
  const extras = econ ? [econ.freight_in_quote === true ? null : n(econ.freight), econ.insurance_in_quote === true ? null : n(econ.insurance), n(econ.inspection)] : [];
  const cost = goods === null ? null : extras.reduce<number>((sum, v) => sum + (v ?? 0), goods);

  // ---- authority ----
  const ownerApproved = parties.some((p) => s(p.note) === OWNER_APPROVED_NOTE);
  const party = supplier ? parties.find((p) => p.data.role === "supplier" && key(p.data.name) === key(supplier)) : undefined;
  const inContact = ["contacted", "replied", "quoted", "selected"].includes(s(party?.data.status || party?.status));

  return {
    id: `${dealId || "deal"}:${econ && econ.role === "agent" ? "agency" : "principal_trade"}`,
    route_type: econ && econ.role === "agent" ? "agency" : "principal_trade",
    represented_org: s(ctx.workspace),
    demand: { source_ids: dealId ? [dealId] : [], buyer, product_spec: s(stage.title) || s(tender?.title) || s(quote?.product), quantity: quote ? n(quote.qty) : null,
      unit: quote && s(quote.unit) ? s(quote.unit) : undefined, deadline: tender ? date(s(tender.deadline).slice(0, 10)) : null, delivery_by: null, status, visibility: null },
    supply: { supplier, technical_fit, requirements },
    evidence,
    economics: { price_type: priced ? "quote" : goods !== null ? "assumption" : "none", sale_price: econ ? n(econ.sale_price) : null, cost,
      capital_need: null, funding_limit: econ ? n(econ.funding_limit) : null },
    authority: { owner_mandate: ownerApproved ? "per_message" : "none", sanctions_alert: false,
      data_rights_ok: legal(LEGAL_RE.data_rights), representation_ok: legal(LEGAL_RE.representation), engagement: inContact ? "in_contact" : "none" },
    time: { now, deadline: date(stage.deadline), quote_valid_until: quote ? date(quote.valid_until) : null, lead_time_days: quote ? n(quote.lead_time_days) : null },
  };
}

export type ContactPolicy = { needs_owner_approval: boolean; conversation_mode: false; reason: string };
/**
 * Read-only: what the send policy says today about any new outgoing message, for display. It asks decideSend with
 * no mandate and conversation mode off, which is how the product runs; it is given no real recipient or text, and
 * its answer is not used by any sending code. Per-message approval in lib/dealagent.ts and the outbox is unchanged.
 */
export function contactPolicy(nowMs: number): ContactPolicy {
  const d = decideSend({ mandate: null, conversationMode: false, message: { recipient: "display-only@example.invalid", channel: "email", text: "display only" }, now: nowMs });
  return { needs_owner_approval: d.decision !== "ALLOW", conversation_mode: false, reason: d.reasons[0] || "" };
}

export type RouteStateView = { evaluation: Evaluation; priority: Priority | null; next_task: NextTask | null; supplier: SupplierChoice; contact: ContactPolicy; not_in_deal_file: string[] };
/** The route state of one deal: the mapping above, then the engine. */
export function routeState(records: DealRecord[], comparison: QuoteComparison, now: string, ctx: DealContext = {}): RouteStateView {
  const route = routeFromDeal(records, comparison, now, ctx);
  const evaluation = evaluateRoute(route);
  return { evaluation, priority: priority(route, evaluation), next_task: evaluation.next_task, supplier: chooseSupplier(records), contact: contactPolicy(Date.parse(now)),
    // fields no deal record holds: the engine sees them as unknown, and the card says so
    not_in_deal_file: ["sanctions screening result", "who else can see the demand", "required delivery date", "capital need"] };
}
