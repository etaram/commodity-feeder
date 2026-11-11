import { createHash } from "crypto";
import { makeAssertion, normaliseEntityKey, type Assertion, type EntityKind } from "@/lib/assertions";
import { appendAssertions, readAssertions } from "@/lib/assertionstore";
import { logEvent } from "@/lib/log";

// Research memory: whatever a person's manual research turns up (research jobs, contact searches, deal reconstruction,
// tender explanations, deal documents) is kept as facts in the assertions ledger, linked to the company or tender it
// is about, so the next person (or the next search) starts from it instead of paying for the same research again.
// Code only: the facts are read out of the finished answer with patterns (e-mails, phones, websites, registration
// numbers, certificates, the next step, the JSON lists the jobs already return); no extra model call. Everything is
// stored as "inferred" with the method "manual research (model with web search), not verified" and the sources the
// research cited, in the researcher's workspace, so it never reads as a verified fact or leaks to another workspace.
export const METHOD = "manual research (model with web search), not verified";
const VERSION = "rm-1";
const TTL_DAYS = 365;

const EMAIL = /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g;
const PHONE = /(?:\+|00)\d[\d\s().-]{7,18}\d/g;
const URL_RX = /https?:\/\/[^\s)\]>"']+/g;
const CERT = /\b(ISO\s?9001|ISO\s?14001|ISO\s?45001|ISO\s?22000|ISO\s?13485|IATF\s?16949|AS\s?9100|FSSC\s?22000|HACCP|GMP|CE mark(?:ing)?|API\s?(?:5L|6D|Q1)|ASME|UL listed|IECEx|ATEX|halal|kosher)\b/gi;
const LEGAL_ID: [string, RegExp][] = [
  ["CNPJ", /\bCNPJ[:\s]*([\d./-]{14,20})/g], ["CIN", /\bCIN[:\s]*([LU]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6})/g], ["GSTIN", /\bGSTIN?[:\s]*(\d{2}[A-Z]{5}\d{4}[A-Z]\d[A-Z\d]{2})/g],
  ["VAT", /\b(?:VAT|USt-?IdNr\.?|TVA|P\.?\s?IVA)[\s.:No]*([A-Z]{2}\s?[\dA-Z]{8,12})/g], ["LEI", /\bLEI[:\s]*([A-Z0-9]{20})\b/g],
  ["Company no.", /\b(?:Company|Registration|Reg\.?) (?:No|Number)\.?[:\s]*([A-Z]{0,2}\d{6,10})/gi],
];
const FREE_MAIL = /@(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|qq|163|126)\./i;
const SKIP_HOST = /(google|bing|wikipedia|linkedin|facebook|twitter|x\.com|youtube|instagram|bloomberg|reuters|dnb\.com|zoominfo|crunchbase|opencorporates|glassdoor|indeed)\./i;

export type Subject = { kind: EntityKind; name: string; country?: string; key?: string };
export type ResearchInput = {
  ws: string; by: string; job: string; subject: Subject; text: string; sources: { url: string; title?: string }[];
  contacts?: { organisation?: string; website?: string; contacts?: { name?: string; role?: string; email?: string; phone?: string; whatsapp?: string; linkedin?: string; channel?: string; source?: string }[] };
  suppliers?: { name?: string; country?: string; type?: string; products?: string; website?: string; source?: string }[];
  product?: string;  // what was searched for (supplier search)
};

const sha = (s: string) => createHash("sha256").update(s).digest("hex");
const clean = (s: string) => String(s || "").replace(/[*_`#>|]/g, " ").replace(/\s+/g, " ").trim();
const addDays = (n: number) => new Date(Date.now() + n * 864e5).toISOString().slice(0, 10);
const host = (u: string) => { try { return new URL(u).hostname.replace(/^www\./, "").toLowerCase(); } catch { return ""; } };
// the company's own core name for domain alignment: "Acme Valves Ltd" -> "acme"
const core = (name: string) => (name.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(/\s+/).find((w) => w.length > 3 && !/^(the|group|international|company|limited|corporation|industries|trading)$/.test(w)) || "");

// Pure: the facts in one finished research answer. Ids are content hashes of (ws, entity, property, value), so the
// same fact found twice is one row; the caller skips ids already in the ledger.
export function extractFacts(r: ResearchInput, now = new Date()): Assertion[] {
  const out: Assertion[] = [];
  const firstSource = r.sources.find((x) => x.url)?.url || "";
  const docHash = sha(r.text).slice(0, 16);
  const subjKey = r.subject.key || normaliseEntityKey(r.subject.name, r.subject.country || "");
  const add = (kind: EntityKind, key: string, property: string, value: string, excerpt: string, url = firstSource, unit = "") => {
    value = clean(value).slice(0, 480);
    if (!key || !value) return;
    const id = "rm-" + sha(`${r.ws}|${key}|${property}|${value.toLowerCase()}`).slice(0, 24);
    if (out.some((a) => a.id === id)) return;
    out.push(makeAssertion({ id, ws: r.ws, entity_kind: kind, entity_key: key, property, value, unit, status: "inferred", reviewed_by: r.by, review_method: METHOD,
      expires: addDays(TTL_DAYS), now, evidence: { url, doc_hash: docHash, excerpt: clean(excerpt).slice(0, 300), method: `${METHOD}; job ${r.job}`, version: VERSION, collected: now.toISOString().slice(0, 10) } }));
  };
  const text = r.text || "";
  const sk = r.subject.kind;
  // 1. the research itself, as a note on the subject: its gist and its next step
  const body = text.replace(/\n(Sources|מקורות):[\s\S]*$/, "");
  const gist = clean(body.split(/\n\s*\n/).find((p) => clean(p).length > 60) || body).slice(0, 480);
  if (gist && r.job !== "deal_docs") add(sk, subjKey, `research:${r.job}`, gist, gist);
  const next = body.match(/(?:Next step|הצעד הבא)\s*:\s*(.+)/i);
  if (next) add(sk, subjKey, "next_step", next[1], next[0]);
  // a tender document's requirements: one fact per requirement, so a later deal on the same tender starts with them
  if (r.job === "deal_docs") for (const l of body.split("\n").map((x) => x.replace(/^\s*-\s*/, "").trim()).filter((x) => x.length > 8).slice(0, 40)) add(sk, subjKey, "requirement", l, l);
  // 2. facts about the subject printed in the answer
  if (sk === "supplier" || sk === "buyer" || sk === "client") {
    const c = core(r.subject.name);
    for (const e of new Set((text.match(EMAIL) || []).map((x) => x.toLowerCase().replace(/[.,;]+$/, "")))) {
      if (FREE_MAIL.test(e) || /\.(png|jpg|gif|svg)$/.test(e)) continue;
      const aligned = c && e.split("@")[1].includes(c);
      add(sk, subjKey, aligned ? "contact_email" : "contact_email_other_domain", e, lineOf(text, e));
    }
    for (const p of new Set((text.match(PHONE) || []).map((x) => x.trim()))) add(sk, subjKey, "contact_phone", p, lineOf(text, p));
    for (const u of new Set((body.match(URL_RX) || []).map((x) => x.replace(/[.,;]+$/, "")))) {
      const h = host(u);
      if (h && c && h.includes(c) && !SKIP_HOST.test(h)) { add(sk, subjKey, "website", `https://${h}/`, lineOf(text, u), u); break; }
    }
    for (const [kind, rx] of LEGAL_ID) for (const m of text.matchAll(rx)) add(sk, subjKey, "legal_id", `${kind} ${m[1].trim()}`, lineOf(text, m[0]));
    for (const m of text.matchAll(CERT)) add(sk, subjKey, "certification", m[0].toUpperCase().replace(/\s+/g, " "), lineOf(text, m[0]));
  }
  // 3. a contact search's JSON: each official channel with the page it was read on
  if (r.contacts?.contacts?.length) {
    const org = r.contacts.organisation || r.subject.name;
    const key = r.subject.key || normaliseEntityKey(org, r.subject.country || "");
    if (r.contacts.website && /^https?:\/\//.test(r.contacts.website)) add(sk, key, "website", r.contacts.website, `official site of ${org}`, r.contacts.website);
    for (const x of r.contacts.contacts.slice(0, 8)) {
      const src = x.source && /^https?:\/\//.test(x.source) ? x.source : firstSource;
      const who = [x.name, x.role].filter(Boolean).join(", ");
      if (x.email) add(sk, key, "contact_email", x.email.toLowerCase(), `${who} ${x.email}`, src);
      if (x.phone) add(sk, key, "contact_phone", x.phone, `${who} ${x.phone}`, src);
      if (x.channel && !x.email) add(sk, key, "contact_channel", x.channel, `${who} ${x.channel}`, src);
      if (x.linkedin && /^https:\/\/([a-z]{2,3}\.)?linkedin\.com\//i.test(x.linkedin)) add(sk, key, "contact_linkedin", x.linkedin, `${who} ${x.linkedin}`, src);
      const wa = String(x.whatsapp || "").replace(/\D/g, "");
      if (wa.length >= 8 && wa.length <= 15) add(sk, key, "contact_whatsapp", "+" + wa, `${who} WhatsApp +${wa}`, src);
    }
  }
  // 4. a supplier search's list: each company named, with what it was found for
  for (const x of r.suppliers || []) {
    if (!x.name || !(x.source || x.website)) continue;
    const key = normaliseEntityKey(x.name, String(x.country || "").toUpperCase());
    const src = /^https?:\/\//.test(x.source || "") ? x.source! : x.website!;
    if (r.product) add("supplier", key, "supplies", r.product, `${x.name}: ${x.products || ""}`, src);
    if (x.type) add("supplier", key, "role", x.type, `${x.name} (${x.type})`, src);
    if (x.website && /^https?:\/\//.test(x.website)) add("supplier", key, "website", x.website, x.name, src);
  }
  return out;
}

function lineOf(text: string, needle: string) {
  const i = text.indexOf(needle);
  if (i < 0) return needle;
  const a = text.lastIndexOf("\n", i) + 1, b = text.indexOf("\n", i);
  return text.slice(a, b < 0 ? undefined : b);
}

// Writes the facts that are not yet in the ledger. Never throws: research must not fail because memory did.
export async function remember(r: ResearchInput): Promise<number> {
  try {
    const facts = extractFacts(r);
    if (!facts.length) return 0;
    const have = new Set((await readAssertions().catch(() => [])).map((a) => a.id));
    const fresh = facts.filter((a) => !have.has(a.id));
    if (fresh.length) await appendAssertions(fresh);
    return fresh.length;
  } catch (e) {
    void logEvent("warn", "research-memory", `not saved (${r.job})`, String(e).slice(0, 200), r.by);
    return 0;
  }
}

// The subject of a research job from what the panel sends: a company (context.supplier / Account / organisation),
// else a tender or project (target_id), else the free text.
export function subjectOf(type: string, target: string, target_id: string, context: Record<string, unknown>): Subject {
  const cx = (context || {}) as Record<string, string>;
  const company = String(cx.supplier || cx.Account || cx.name || cx.organisation || cx.buyer_name || "").trim();
  const country = String(cx.country || cx.Country || "").trim().slice(0, 3).toUpperCase();
  if (/company|find_contact|outreach/.test(type) && company) return { kind: "supplier", name: company, country };
  if (/company/.test(type)) return { kind: "supplier", name: String(target).replace(/\s*\([A-Z]{3}\)\s*$/, "").replace(/^Business intelligence:\s*/i, ""), country: (String(target).match(/\(([A-Z]{3})\)\s*$/) || [])[1] || country };
  if (target_id) return { kind: "project", name: String(target), key: `tender:${String(target_id).slice(0, 80)}` };
  return { kind: "product", name: String(target).slice(0, 120) };
}

// Research people ran before memory existed: the finished rows of 'Panel Jobs' (the original workspace's private tab)
// read through the same extraction, idempotent on ids, a bounded number per call. Code only.
export async function backfillJobs(limit = 300): Promise<{ jobs: number; facts: number }> {
  const { readRanges, ENGINE_SHEET } = await import("@/lib/sheets");
  const { DEFAULT_WS, asWs } = await import("@/lib/auth");
  // rows written by an account of another workspace (before the tab was closed to them) are not the original
  // workspace's research: they are skipped, never adopted. If the accounts cannot be read, nothing is copied.
  const { listUsers } = await import("@/lib/users");
  const foreign = new Set((await listUsers()).filter((u) => asWs(u.workspace) !== DEFAULT_WS).map((u) => u.email.toLowerCase()));
  const g = (await readRanges(ENGINE_SHEET, ["'Panel Jobs'!A2:L5000"]).catch(() => null))?.[0] || [];
  const have = new Set((await readAssertions().catch(() => [])).map((a) => a.id));
  const fresh: Assertion[] = [];
  let jobs = 0;
  for (const r of g) {
    if (fresh.length >= limit) break;
    const [, stamp, type, target_id, target, ctx, , status, result] = r.map((x) => String(x ?? ""));
    if (status !== "done" || !result || result.length < 40) continue;
    let context: Record<string, unknown> = {};
    try { context = JSON.parse(ctx || "{}"); } catch { context = {}; }
    const by = (String(r[11] || "").match(/[\w.+-]+@[\w.-]+/) || [""])[0];
    if (by && foreign.has(by.toLowerCase())) continue;
    const sources = [...result.matchAll(/https?:\/\/[^\s)\]>"']+/g)].slice(-8).map((m) => ({ url: m[0] }));
    let contacts: ResearchInput["contacts"];
    if (type === "find_contact") { try { contacts = JSON.parse((result.match(/\{[\s\S]*\}/) || ["{}"])[0]); } catch { contacts = undefined; } }
    const when = /^\d{4}-\d{2}-\d{2}/.test(stamp) ? new Date(stamp.replace(" ", "T") + ":00Z") : new Date();
    const facts = extractFacts({ ws: DEFAULT_WS, by, job: type || "other", subject: subjectOf(type, target, target_id, context), text: result, sources, contacts }, when);
    const add = facts.filter((a) => !have.has(a.id));
    add.forEach((a) => have.add(a.id));
    if (add.length) { fresh.push(...add); jobs++; }
  }
  if (fresh.length) await appendAssertions(fresh.slice(0, limit));
  return { jobs, facts: Math.min(fresh.length, limit) };
}
