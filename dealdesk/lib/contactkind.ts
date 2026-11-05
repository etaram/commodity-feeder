// Contact provenance for one supplier (mirrors leads/contacts.py email_kind): what kind of channel the e-mail is
// (a generic sales box, a named person, other) and whether its domain is the company's own website domain.
// Valid syntax is not deliverability; a different domain is a reason to check, never a verdict.
const GENERIC = /^(info|sales|export|exports|contact|office|admin|mail|enquir\w*|inquir\w*|hello|marketing|support|service|trade|commercial|business|import|purchase|procurement|tender\w*)\b/i;
const FREE = /(gmail|yahoo|hotmail|outlook|live|icloud|aol|gmx|mail|yandex|qq|163|126|sina)\./i;
const root = (d: string) => (/\.(co|com|org|net|gov|ac)\.[a-z]{2}$/.test(d) ? d.split(".").slice(-3) : d.split(".").slice(-2)).join(".");
export function emailKind(emails: string, website = ""): { kind: string; domain: string } {
  const e = String(emails || "").split(";")[0].trim().toLowerCase();
  if (!e.includes("@")) return { kind: "", domain: "" };
  const [box, dom] = e.split("@");
  const kind = GENERIC.test(box) ? "generic sales channel" : /^[a-z]+[._-][a-z]+$/.test(box) ? "named contact" : "other";
  const site = String(website || "").toLowerCase().replace(/^https?:\/\/(www\.)?/, "").split("/")[0];
  const domain = FREE.test(dom) ? "free mail" : site ? (root(site) === root(dom) ? "aligned" : "different domain") : "";
  return { kind, domain };
}
