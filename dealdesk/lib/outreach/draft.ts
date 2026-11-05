import { sha } from "./store";
import type { Account, CampaignPlan, Template } from "./types";

// Evidence-grounded drafts: deterministic template filling from approved claims, an identification block and an
// opt-out line appended in code (a model can never remove them), and at most one bounded model call to adapt wording,
// whose output is validated in code and dropped (falling back to the deterministic text) when it adds anything.

// Never negotiate prices, make commitments or promise unsupported performance. Checked on claims, offer, templates,
// every rendered message and every model adaptation.
export const FORBIDDEN: [RegExp, string][] = [
  [/[$€£₪¥]\s?\d|\d[\d,.]*\s?(usd|eur|gbp|nis|ils|cny|rmb|dollars?|euros?|shekels?)\b/i, "price or amount"],
  [/\b(prices?|priced|pricing|cheap\w*|lowest|best rates?|per (ton|tonne|unit|kg|mt|piece))\b/i, "price talk"],
  [/\b(discount\w*|rebate\w*|special offer|free of charge|at no cost|\d+\s?% off)\b/i, "discount"],
  [/\b(guarantee\w*|warrant(y|ies|ed)|risk[- ]free|money[- ]back|100\s?%)/i, "guarantee"],
  [/\b(deliver\w*|ship\w*|lead time|dispatch\w*)\b[^.\n]{0,40}\b(within|in|by|under)\s+\d+\s*(hours?|days?|weeks?|months?)\b/i, "delivery promise"],
  [/\b(we|i) (will|can|shall) (deliver|supply|ship|ensure|guarantee|secure|commit)\b|\bwe commit\b|\bcommitted to deliver/i, "commitment"],
  [/\b(increase|boost|cut|reduce|save|double|triple|improve)\w*\b[^.\n]{0,40}\d+\s?(%|percent|x\b)/i, "unsupported performance"],
  [/\b(binding offer|payment terms|contract terms|exclusive (deal|rights)|best and final)\b/i, "negotiation"],
  [/(מחיר|הנחה|מבטיח|מתחייב|אחריות מלאה)/, "price, discount or commitment (Hebrew)"],
];

export function forbiddenHits(text: string): string[] {
  const out: string[] = [];
  for (const [re, label] of FORBIDDEN) if (re.test(text)) out.push(label);
  return out;
}

const OPT_OUT_RE = /(unsubscribe|opt[- ]?out|not (to )?hear from|not contact you|stop (contacting|emailing)|will not follow up|won't follow up|הסר)/i;

// core: the filled template without the footer (the base an adaptation is checked against).
export type Rendered = { subject: string; body: string; core: string; claims_used: string[]; template_id: string; errors: string[] };

const VAR_RE = /\{\{\s*([a-z_]+)(?::([a-z0-9_-]+))?(?:\|([^}]*))?\s*\}\}/gi;
const BASE_FIELDS = ["first_name", "last_name", "contact_name", "company", "country", "title"];

export function templateFor(plan: CampaignPlan, step: number, channel: "email" | "linkedin", kind?: Template["kind"]): Template | null {
  return plan.templates.find((t) => t.step === step && t.channel === channel && (!kind || t.kind === kind)) || null;
}

function fill(text: string, plan: CampaignPlan, acc: Account, used: Set<string>, errors: string[]): string {
  return text.replace(VAR_RE, (_m, name: string, arg: string | undefined, dflt: string | undefined) => {
    const n = name.toLowerCase();
    if (n === "claim") {
      const c = plan.claims.find((x) => x.id === arg);
      if (!c) { errors.push(`unknown claim ${arg}`); return ""; }
      used.add(c.id);
      return c.text;
    }
    if (n === "offer") return plan.offer;
    if (n === "sender_name") return plan.sender.name;
    if (n === "sender_org") return plan.sender.org;
    let v = "";
    if (BASE_FIELDS.includes(n)) v = String((acc as unknown as Record<string, string>)[n] || "");
    else if (plan.personalization_fields.includes(n)) v = String(acc.fields?.[n] || "");
    else { errors.push(`placeholder {{${n}}} is not an allowed personalization field`); return ""; }
    v = v.replace(/[\r\n]+/g, " ").trim().slice(0, 120);
    if (!v && dflt === undefined) errors.push(`missing value for {{${n}}}`);
    return v || (dflt ?? "").trim();
  });
}

export function identificationBlock(plan: CampaignPlan): string {
  const s = plan.sender;
  return [`${s.name}${s.title ? ", " + s.title : ""}`, s.org, s.email + (s.address ? " | " + s.address : "")].join("\n");
}

// Appends identification and the opt-out line. Done in code after any adaptation.
export function withFooter(body: string, plan: CampaignPlan, channel: "email" | "linkedin"): string {
  if (channel === "linkedin") return `${body.trim()}\n${plan.sender.name}, ${plan.sender.org}. ${plan.linkedin_opt_out_line}`;
  return `${body.trim()}\n\n--\n${identificationBlock(plan)}\n${plan.opt_out_line}`;
}

export function renderMessage(plan: CampaignPlan, acc: Account, step: number, channel: "email" | "linkedin" = "email", kind?: Template["kind"]): Rendered {
  const t = templateFor(plan, step, channel, kind);
  if (!t) return { subject: "", body: "", core: "", claims_used: [], template_id: "", errors: [`no ${channel} template for step ${step}`] };
  const used = new Set<string>(), errors: string[] = [];
  const subject = fill(t.subject, plan, acc, used, errors).replace(/\s+/g, " ").trim();
  const core = fill(t.body, plan, acc, used, errors).trim();
  return { subject, body: withFooter(core, plan, channel), core, claims_used: [...used], template_id: t.id, errors };
}

// Every check a message must pass before preview approval and again immediately before it is handed to a transport.
export type Check = { name: string; ok: boolean; detail: string };
export function validateMessage(m: { subject: string; body: string; from_email: string; from_name: string }, plan: CampaignPlan, channel: "email" | "linkedin" = "email"): Check[] {
  const body = m.body || "";
  const claimText = plan.claims.map((c) => c.text);
  // claim texts were checked when the plan was saved; strip them so a claim is not double counted
  let rest = body;
  for (const c of claimText) if (c) rest = rest.split(c).join(" ");
  const hits = forbiddenHits(`${m.subject}\n${rest}`);
  const s = plan.sender;
  const checks: Check[] = [
    { name: "opt_out_line", ok: channel === "linkedin" ? body.includes(plan.linkedin_opt_out_line) && OPT_OUT_RE.test(plan.linkedin_opt_out_line) : body.includes(plan.opt_out_line) && OPT_OUT_RE.test(plan.opt_out_line), detail: "every message carries the opt-out line" },
    { name: "sender_identification", ok: body.includes(s.name) && body.includes(s.org) && (channel === "linkedin" || body.includes(s.email)), detail: "sender name, organisation and address are in the message" },
    { name: "sender_matches", ok: channel === "linkedin" || (m.from_email.toLowerCase() === s.email.toLowerCase() && m.from_name === s.name), detail: "the From identity is the plan's sender, never another person" },
    { name: "no_forbidden_terms", ok: hits.length === 0, detail: hits.length ? `found: ${[...new Set(hits)].join(", ")}` : "no prices, discounts, guarantees, delivery promises or commitments" },
    { name: "no_unfilled_placeholders", ok: !/\{\{|\}\}/.test(`${m.subject}${body}`), detail: "all placeholders filled" },
    { name: "subject", ok: channel === "linkedin" || (m.subject.length > 0 && m.subject.length <= 160), detail: "subject present, at most 160 chars" },
    { name: "length", ok: channel === "linkedin" ? body.length <= 1900 : body.length <= 8000, detail: "within length limits" },
  ];
  return checks;
}
export const passes = (c: Check[]) => c.every((x) => x.ok);

// ---- optional wording adaptation (at most one model call per draft) ----

const words = (t: string) => (t.toLowerCase().match(/[\p{L}\p{N}]{4,}/gu) || []);
const numbers = (t: string) => (t.match(/\d+(?:[.,]\d+)?/g) || []);
const sentences = (t: string) => t.split(/(?<=[.!?])\s+|\n+/).map((x) => x.trim()).filter((x) => x.length > 0);

// The adapted core (without footer) must: keep every used claim verbatim, add no number, no forbidden term, no
// sentence whose content words are mostly new, and stay within 130% of the deterministic length.
export function validateAdaptation(base: string, adapted: string, claimsUsed: string[], plan: CampaignPlan): string[] {
  const errs: string[] = [];
  for (const id of claimsUsed) {
    const c = plan.claims.find((x) => x.id === id);
    if (c && !adapted.includes(c.text)) errs.push(`claim ${id} not kept verbatim`);
  }
  const baseNums = new Set(numbers(base));
  for (const n of numbers(adapted)) if (!baseNums.has(n)) errs.push(`new number ${n}`);
  let rest = adapted;
  for (const c of plan.claims) rest = rest.split(c.text).join(" ");
  const hits = forbiddenHits(rest);
  if (hits.length) errs.push(`forbidden: ${hits.join(", ")}`);
  const vocab = new Set(words(base));
  for (const s of sentences(adapted)) {
    const w = words(s);
    if (w.length < 3) continue;
    const known = w.filter((x) => vocab.has(x)).length / w.length;
    if (known < 0.6) errs.push(`new content: "${s.slice(0, 80)}"`);
  }
  if (adapted.length > base.length * 1.3 + 40) errs.push("too long");
  if (/\{\{|\}\}/.test(adapted)) errs.push("placeholder left");
  return errs;
}

export type ModelFn = (prompt: string) => Promise<string>;
const cache = new Map<string, { subject: string; body: string } | null>();

// Returns validated adapted wording or null (use the deterministic text). The model sees only the draft and the
// approved claims; its JSON output is parsed and checked in code. Cached by content hash.
export async function adaptWording(plan: CampaignPlan, acc: Account, step: number, model: ModelFn): Promise<{ adapted: { subject: string; body: string } | null; rejected: string[] }> {
  const t = templateFor(plan, step, "email");
  if (!t) return { adapted: null, rejected: ["no template"] };
  const used = new Set<string>(), errors: string[] = [];
  const subject = fill(t.subject, plan, acc, used, errors).trim();
  const core = fill(t.body, plan, acc, used, errors).trim();
  if (errors.length) return { adapted: null, rejected: errors };
  const key = sha(JSON.stringify([subject, core, [...used], plan.claims]));
  if (cache.has(key)) { const c = cache.get(key)!; return { adapted: c, rejected: c ? [] : ["cached rejection"] }; }
  const keep = plan.claims.filter((c) => used.has(c.id)).map((c) => `- ${c.text}`).join("\n");
  const prompt = `Lightly improve the wording of this outreach email for readability. Rules: do not add any fact, number, price, discount, guarantee, delivery time or commitment; keep these sentences exactly as written:\n${keep || "(none)"}\nDo not add a signature or opt-out line. Return only JSON {"subject": "...", "body": "..."}.\n\nSUBJECT: ${subject}\nBODY:\n${core}`.slice(0, 6000);
  let out: { subject: string; body: string } | null = null;
  const rejected: string[] = [];
  try {
    const raw = await model(prompt);
    const j = JSON.parse(raw.slice(raw.indexOf("{"), raw.lastIndexOf("}") + 1));
    const s2 = String(j.subject || "").trim().slice(0, 160), b2 = String(j.body || "").trim();
    if (!s2 || !b2) rejected.push("empty output");
    rejected.push(...validateAdaptation(core, b2, [...used], plan), ...validateAdaptation(subject, s2, [], plan).filter((e) => e !== "too long"));
    if (!rejected.length) out = { subject: s2, body: b2 };
  } catch (e) {
    rejected.push(`model output unusable: ${String(e).slice(0, 80)}`);
  }
  cache.set(key, out);
  return { adapted: out, rejected };
}

// Default model hook for routes: one bounded call through the shared client.
export async function defaultModel(prompt: string): Promise<string> {
  const { claude } = await import("@/lib/anthropic");
  const { text } = await claude({ max_tokens: 700, messages: [{ role: "user", content: prompt }] });
  return text;
}
