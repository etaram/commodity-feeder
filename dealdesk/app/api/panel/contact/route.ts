import { logEvent } from "@/lib/log";
import { NextRequest, NextResponse } from "next/server";
import { cookies } from "next/headers";
import { verifySession } from "@/lib/auth";
import { lookupContact } from "@/lib/sheets";
import { cleanPhones } from "@/lib/phone";
import { emailKind } from "@/lib/contactkind";

// Contact details for one supplier, read from the private Supplier Universe sheet only when a signed-in user opens it.
const cache = new Map<string, { at: number; v: Record<string, string> | null }>();

export async function POST(req: NextRequest) {
  if (!verifySession((await cookies()).get("dd_session")?.value)) return NextResponse.json({ ok: false }, { status: 401 });
  const { name, country } = await req.json().catch(() => ({}));
  if (typeof name !== "string" || !name.trim()) return NextResponse.json({ ok: false }, { status: 400 });
  const k = `${name}|${country || ""}`;
  const hit = cache.get(k);
  if (hit && Date.now() - hit.at < 3600_000) return NextResponse.json({ ok: true, contact: hit.v });
  try {
    let v = await lookupContact(name.trim(), String(country || "").trim());
    if (!v && country) v = await lookupContact(name.trim(), "");
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
