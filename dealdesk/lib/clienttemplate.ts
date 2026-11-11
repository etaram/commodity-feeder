import type { Claim, Field, Question } from "@/lib/dossier";

// Technical templates for client products, and the code that reads client material as data.
// A template lists the parameters a buyer of that product class asks for. A parameter the client's material does not
// state becomes a question to the client; nothing is filled in from general knowledge. The membrane process
// (RO / NF / UF / MF) is "unknown" until a claim states it in words: an application word such as "desalination" or
// "water treatment" says nothing about the process and is never used to infer it.

export type MembraneType = "RO" | "NF" | "UF" | "MF";
export type Technical = {
  template: "membrane" | null;
  membrane_types: MembraneType[];            // only what a claim states
  membrane_type: string;                     // "unknown" when nothing states it
  type_stated_in: { claim_id: string; source_ref: string; type: MembraneType }[];
  questions: Question[];                     // the parameters the material does not state
};

const TECH_FIELDS = new Set<Field>(["products_services", "capabilities", "limitations", "use_cases", "differentiators", "certifications", "lead_times"]);
const IS_MEMBRANE = /\bmembranes?\b|\breverse[- ]osmosis\b|\b(nano|ultra|micro)-?filtration\b/i;
// abbreviations are matched in upper case only ("RO", "SWRO"), so ordinary words never count
const TYPE_RX: [MembraneType, RegExp, RegExp][] = [
  ["RO", /\breverse[- ]osmosis\b/i, /\b(?:SW|BW)?RO\b/],
  ["NF", /\bnano-?filtration\b/i, /\bNF\b/],
  ["UF", /\bultra-?filtration\b/i, /\bUF\b/],
  ["MF", /\bmicro-?filtration\b/i, /\bMF\b/],
];
export const membraneTypesIn = (value: string): MembraneType[] => TYPE_RX.filter(([, word, abbr]) => word.test(value) || abbr.test(value)).map(([t]) => t);

type Param = { id: string; label: string; stated: RegExp; question: string; market: boolean };
export const MEMBRANE_TEMPLATE: Param[] = [
  { id: "format", label: "Element format and size", stated: /spiral[- ]wound|hollow[- ]fib(er|re)|flat[- ]sheet|tubular|\b(2540|4040|8040)\b|\b\d+(\.\d+)?[- ]?(inch|in\.|")/i, question: "What is the element format and size (spiral wound, hollow fibre, flat sheet, tubular; for example 4040 or 8040)?", market: true },
  { id: "material", label: "Membrane material", stated: /polyamide|thin[- ]film|\bTFC\b|\bPVDF\b|\bPES\b|polyethersulf|polysulf|cellulose acetate|ceramic|\bPTFE\b/i, question: "What is the membrane material (for example polyamide thin film composite, PVDF, PES, ceramic)?", market: false },
  { id: "feed", label: "Feed water", stated: /sea ?water|brackish|feed ?water|\btds\b|\bppm\b|mg\/l|waste ?water|surface water|salinity|effluent/i, question: "Which feed water is each model designed for (seawater, brackish, surface water, wastewater), and up to what salinity (TDS, mg/l)?", market: true },
  { id: "rejection", label: "Rejection or pore size", stated: /rejection|removal rate|permeate (quality|tds)|\bmwco\b|pore size|\bmicrons?\b|µm|daltons?|log removal/i, question: "What is the stated salt rejection (RO, NF) or the pore size / molecular weight cut-off (UF, MF), and under which test conditions?", market: true },
  { id: "flow", label: "Permeate flow or flux", stated: /m3\/d|m³\/d|m3\/day|m³\/day|\bgpd\b|m3\/h|m³\/h|\blmh\b|\bflux\b|permeate flow|\bcapacity\b/i, question: "What is the permeate flow per element (m3/day or GPD) or the design flux, and under which test conditions?", market: true },
  { id: "pressure", label: "Operating pressure", stated: /\bbar\b|\bpsi\b|\bmpa\b|operating pressure|max(imum)? pressure/i, question: "What are the operating pressure and the maximum pressure (bar or psi)?", market: false },
  { id: "limits", label: "Operating limits", stated: /°\s?c\b|temperature|\bph\b|chlorine|turbidity|\bsdi\b/i, question: "What are the operating limits: maximum temperature, pH range (operation and cleaning), free chlorine tolerance, feed SDI or turbidity?", market: false },
  { id: "recovery", label: "Recovery", stated: /\brecovery\b/i, question: "What recovery does the client state per element or per system?", market: false },
  { id: "energy", label: "Energy use", stated: /kwh|energy (use|consumption|recovery)|specific energy/i, question: "Is an energy figure stated (kWh per m3), and for which system configuration?", market: false },
  { id: "approvals", label: "Drinking-water approvals", stated: /\bnsf\b|ansi\s?61|\bwras\b|\bkiwa\b|\bacs\b|potable|drinking[- ]water (approval|certif)/i, question: "Which drinking-water contact approvals does each model hold (for example NSF/ANSI 61, WRAS, KIWA, ACS): certificate number, issuer and validity?", market: true },
  { id: "compatibility", label: "Interchangeability", stated: /interchangeab|compatible with|replaces|equivalent to|drop[- ]in|pressure vessels?/i, question: "Which existing elements or pressure vessels are the client's elements interchangeable with?", market: false },
  { id: "warranty", label: "Warranty and service life", stated: /warranty|service life|life ?time|years of operation/i, question: "What warranty and expected service life does the client give, and on what conditions?", market: false },
];

export function technicalOf(claims: Claim[]): Technical {
  const live = claims.filter((c) => !c.rejected && TECH_FIELDS.has(c.field));
  if (!live.some((c) => IS_MEMBRANE.test(c.value))) return { template: null, membrane_types: [], membrane_type: "unknown", type_stated_in: [], questions: [] };
  const stated = live.flatMap((c) => membraneTypesIn(c.value).map((type) => ({ claim_id: c.id, source_ref: c.source_ref, type })));
  const types = TYPE_RX.map(([t]) => t).filter((t) => stated.some((s) => s.type === t));
  const text = live.map((c) => c.value).join("\n");
  const q = (id: string, question: string, why: string, market: boolean): Question => ({ id: `QT-membrane-${id}`, question, why, changes_target_market: market, field: "capabilities", origin: "code", template: "membrane" });
  const questions: Question[] = [];
  if (!types.length) questions.push(q("type", "Which membrane process is each product: reverse osmosis (RO), nanofiltration (NF), ultrafiltration (UF) or microfiltration (MF)?", "membrane template: the material names a membrane product but does not state the process; the type stays unknown until the client states it", true));
  for (const p of MEMBRANE_TEMPLATE) if (!p.stated.test(text)) questions.push(q(p.id, p.question, `membrane template: ${p.label.toLowerCase()} is not stated in the client's material`, p.market));
  return { template: "membrane", membrane_types: types, membrane_type: types.length ? types.join(" / ") : "unknown", type_stated_in: stated, questions };
}

// ------------------------------------------------------------------ instruction-like text inside client material
// A deck is data. A sentence in it that addresses the reader or the system ("ignore previous instructions", "email
// every contact") is recorded as a flagged quotation for the reviewer and never acted on.
const INSTRUCTION: [RegExp, string][] = [
  [/\b(ignore|disregard|forget|override|bypass)\b[^.\n]{0,40}\b(previous|prior|above|earlier|all|any|your|the system|system)\b[^.\n]{0,30}\b(instructions?|prompts?|rules?|guidelines?|policies|context)\b/i, "asks the reader to ignore its instructions"],
  [/\b(you are now|from now on you|act as (an?|the) |pretend to be|new instructions?:|system prompt|developer message|\bas an ai\b)/i, "tries to give the reader a new role or new instructions"],
  [/(^|[.!?:;]\s*|\b(and|then|please|now|must|should|to)\s+)(send|e-?mail|forward|share|export|upload|post|leak|disclose)\b[^.\n]{0,60}\b(every|all|each)\b[^.\n]{0,30}\b(contacts?|customers?|recipients?|leads?|prospects?|suppliers?|buyers?)\b/i, "asks for a message or data to be sent to contacts"],
  [/(^|[.!?:;]\s*|\b(and|then|please|now|must|should|to)\s+)(approve|verify|mark|upgrade|set)\b[^.\n]{0,40}\b(all|every|each|this|these)\b[^.\n]{0,30}\b(claims?|facts?|as verified|as approved)\b/i, "asks for claims to be approved or upgraded"],
  [/\b(do not|don't|never)\b[^.\n]{0,30}\b(tell|inform|show|mention|reveal)\b[^.\n]{0,30}\b(the )?(user|reviewer|analyst|operator|admin)\b/i, "asks for something to be hidden from the reviewer"],
];
export const INSTRUCTION_FLAG = "instruction-like text: kept as a quotation, never acted on, cannot be approved";
export function instructionLike(text: string): { quote: string; reason: string }[] {
  const out: { quote: string; reason: string }[] = [];
  for (const line of String(text || "").split(/\n+/)) {
    const l = line.replace(/\s+/g, " ").trim();
    if (l.length < 12) continue;
    for (const [rx, reason] of INSTRUCTION) if (rx.test(l)) { out.push({ quote: l.slice(0, 400), reason }); break; }
  }
  return out;
}
