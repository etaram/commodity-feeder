import { NextRequest, NextResponse } from "next/server";
import { gate } from "@/lib/gate";
import { logActivity } from "@/lib/activity";
import { appendAssertion, readAssertions } from "@/lib/assertionstore";
import { ENTITY_KINDS, PUBLIC_WS, expire, filterRows, makeAssertion, normaliseEntityKey, quarantine, resolve, visibleTo, type EntityKind, type Evidence } from "@/lib/assertions";

export const dynamic = "force-dynamic";

const bad = (error: string, status = 400) => NextResponse.json({ ok: false, error }, { status });
const PROP = /^[a-z][a-z0-9_]{0,39}$/;

// GET ?entity=<name or key>&country=&property=&status= (viewer)
// -> {ok, rows}: this workspace's rows plus public rows, resolved (latest non-superseded version per claim, human
// review outranking model review), with rows past their expiry returned as status "expired". `entity` may be a raw
// company name (normalised with `country`) or an exact entity_key.
export async function GET(req: NextRequest) {
  const { s, res } = await gate("viewer");
  if (!s) return res;
  const q = req.nextUrl.searchParams;
  const entity = String(q.get("entity") || "").trim().slice(0, 200), country = String(q.get("country") || "").trim().slice(0, 3);
  const property = String(q.get("property") || "").trim().slice(0, 40), status = String(q.get("status") || "").trim().slice(0, 12);
  try {
    const all = visibleTo(await readAssertions(), s.ws);
    const keys = entity ? [entity, normaliseEntityKey(entity, country)] : [];
    const mine = entity ? all.filter((r) => keys.includes(r.entity_key)) : all;
    const rows = filterRows(expire(resolve(mine)), { property, status }).sort((a, b) => a.entity_key.localeCompare(b.entity_key) || a.property.localeCompare(b.property) || b.created.localeCompare(a.created));
    return NextResponse.json({ ok: true, rows: rows.slice(0, 2000), total: rows.length });
  } catch (e) {
    return bad(String(e).slice(0, 200), 500);
  }
}

// POST (analyst), two shapes, ws always taken from the session and never from the body:
//  {entity_kind, entity_key|entity+country, property, value, unit?, status: observed|inferred, evidence: {url, excerpt, published?, publisher?, doc_hash?}, expires?}
//     -> appends a new claim with review_method "human entry"; returns {ok, row}
//  {quarantine: <id>, status: disputed|rejected, reason}
//     -> appends a superseding row for that one claim; returns {ok, row}
export async function POST(req: NextRequest) {
  const { s, res } = await gate("analyst");
  if (!s) return res;
  const b = await req.json().catch(() => ({}));
  try {
    if (b.quarantine) {
      const id = String(b.quarantine).slice(0, 60), status = b.status === "rejected" ? "rejected" : b.status === "disputed" ? "disputed" : "";
      const reason = String(b.reason || "").replace(/[\r\n]+/g, " ").trim().slice(0, 500);
      if (!status || !reason) return bad("status (disputed or rejected) and reason are required");
      const rows = await readAssertions();
      const src = rows.find((r) => r.id === id);
      if (!src) return bad("unknown assertion id", 404);
      // own rows: any analyst of the workspace; public rows: admins only (they are shared by every workspace)
      if (src.ws !== s.ws && !(src.ws === PUBLIC_WS && s.role === "admin")) return bad("not in your workspace", 403);
      if (src.status === status && src.evidence.reason === reason) return bad("already in that state");
      const row = quarantine(rows, id, reason, s.email, status);
      if (!row) return bad("unknown assertion id", 404);
      await appendAssertion(row);
      await logActivity(s, "assertion_quarantine", `${src.entity_key} | ${src.property} | ${src.value}`.slice(0, 300), `${status}: ${reason}`.slice(0, 300));
      return NextResponse.json({ ok: true, row });
    }
    const kind = String(b.entity_kind || "supplier");
    if (!(ENTITY_KINDS as readonly string[]).includes(kind)) return bad(`entity_kind must be one of ${ENTITY_KINDS.join(", ")}`);
    const entity_key = String(b.entity_key || "").trim().slice(0, 200) || normaliseEntityKey(String(b.entity || ""), String(b.country || ""));
    if (!entity_key || entity_key === "|") return bad("entity_key or entity is required");
    const property = String(b.property || "").trim().toLowerCase();
    if (!PROP.test(property)) return bad("property must be a short snake_case name");
    const value = String(b.value ?? "").replace(/[\r\n]+/g, " ").trim().slice(0, 500);
    if (!value) return bad("value is required");
    const status = b.status === "inferred" ? "inferred" : b.status === "observed" ? "observed" : "";
    if (!status) return bad("status must be observed or inferred");
    const e = (b.evidence && typeof b.evidence === "object" ? b.evidence : {}) as Record<string, unknown>;
    const url = String(e.url || "").trim().slice(0, 300);
    if (url && !/^https?:\/\//i.test(url)) return bad("evidence.url must be an http(s) URL");
    const excerpt = String(e.excerpt || "").replace(/\s+/g, " ").trim().slice(0, 1000);
    if (!url && !excerpt && !e.doc_hash) return bad("evidence needs a url, an excerpt or a doc_hash");
    const date = (v: unknown) => (/^\d{4}-\d{2}-\d{2}$/.test(String(v || "")) ? String(v) : "");
    const evidence: Evidence = { url, excerpt, publisher: String(e.publisher || "").slice(0, 120), published: date(e.published), doc_hash: String(e.doc_hash || "").slice(0, 80),
      verified: new Date().toISOString().slice(0, 10), method: "human entry", version: "ledger-1" };
    const row = makeAssertion({ ws: s.ws, entity_kind: kind as EntityKind, entity_key, property, value, unit: String(b.unit || ""), status, evidence,
      review_method: "human entry", reviewed_by: s.email, expires: date(b.expires) });
    await appendAssertion(row);
    await logActivity(s, "assertion_add", `${entity_key} | ${property} | ${value}`.slice(0, 300), status);
    return NextResponse.json({ ok: true, row });
  } catch (e) {
    return bad(String(e).slice(0, 200), 500);
  }
}
