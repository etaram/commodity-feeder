import { auditSession } from "@/lib/gate";
import { logEvent } from "@/lib/log";
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { lookupContact } from "@/lib/sheets";
import { cleanPhones } from "@/lib/phone";
import { emailKind } from "@/lib/contactkind";
import { readAssertions } from "@/lib/assertionstore";
import { expire, normaliseEntityKey, resolve, visibleTo } from "@/lib/assertions";
import { DEFAULT_WS } from "@/lib/auth";

// What earlier manual research found for this company (assertions ledger, this workspace), used only to fill what
// the supplier record lacks, and labelled as research so it never reads as the registry or the company's own record.
async function fromResearch(name: string, country: string, ws: string): Promise<Record<string, string>> {
  const keys = [normaliseEntityKey(name, country), normaliseEntityKey(name, "")];
  const rows = expire(resolve(visibleTo(await readAssertions(), ws).filter((a) => keys.includes(a.entity_key)))).filter((a) => a.status === "observed" || a.status === "inferred");
  const pick = (p: string) => rows.filter((a) => a.property === p).sort((a, b) => b.created.localeCompare(a.created)).map((a) => a.value);
  const out: Record<string, string> = {};
  const em = pick("contact_email"), ph = pick("contact_phone"), web = pick("website");
  if (em.length) out.email = em.slice(0, 2).join("; ");
  if (ph.length) out.phone = ph[0];
  const li = pick("contact_linkedin"), wa = pick("contact_whatsapp");
  if (li.length) out.linkedin = li[0];
  if (wa.length) out.whatsapp = wa.slice(0, 2).join(" ");
  if (web.length) { out.website = web[0]; out.website_source = "earlier research (not verified)"; }
  if (Object.keys(out).length) out.contact_source = "earlier research (not verified)";
  return out;
}

// Contact details for one supplier, read from the private Supplier Universe sheet only when a signed-in user opens it.
const cache = new Map<string, { at: number; v: Record<string, string> | null }>();

export async function POST(req: NextRequest) {
  const sess = (verifySession((await cookies()).get("dd_session")?.value) || (await auditSession()));
  if (!sess) return NextResponse.json({ ok: false }, { status: 401 });
  const ws = sess.ws || DEFAULT_WS;
  const { name, country } = await req.json().catch(() => ({}));
  if (typeof name !== "string" || !name.trim()) return NextResponse.json({ ok: false }, { status: 400 });
  const k = `${ws}|${name}|${country || ""}`;
  const hit = cache.get(k);
  if (hit && Date.now() - hit.at < 3600_000) return NextResponse.json({ ok: true, contact: hit.v });
  try {
    let v = await lookupContact(name.trim(), String(country || "").trim());
    if (!v && country) v = await lookupContact(name.trim(), "");
    // gaps filled from earlier research, never overwriting what the record has
    const rs = await fromResearch(name.trim(), String(country || "").trim(), ws).catch(() => ({} as Record<string, string>));
    if (Object.keys(rs).length) {
      const base: Record<string, string> = v || {};
      const filled = Object.fromEntries(Object.entries(rs).filter(([kk]) => !base[kk]));
      if (Object.keys(filled).some((kk) => ["email", "phone", "website", "linkedin", "whatsapp"].includes(kk))) v = { ...base, ...filled };
    }
    if (v && v.phone) v = { ...v, phone: cleanPhones(v.phone, String(v.country || country || "")) || v.phone };
    if (v && v.email) { const k = emailKind(v.email, v.website); v = { ...v, email_kind: k.kind, email_domain: k.domain }; }
    if (cache.size > 2000) cache.delete(cache.keys().next().value as string);
    cache.set(k, { at: Date.now(), v });
    return NextResponse.json({ ok: true, contact: v });
  } catch (e) {
    await logEvent("error", "contact", String(e).slice(0, 200));
    return NextResponse.json({ ok: false, error: String(e).slice(0, 200) }, { status: 502 });
  }
}
