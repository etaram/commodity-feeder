// Assertions ledger (spec sections 6 and 7). Run: npx esbuild tests/assertions.test.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=... && node ...
import { assertionsFromVerifiedCaps, canonicalUrl, countIndependent, expire, fromGrid, fromRow, isMirror, makeAssertion, normaliseEntityKey, quarantine, resolve, toRow, visibleTo, filterRows, PUBLIC_WS, type Assertion } from "@/lib/assertions";
import { DEFAULT_WS } from "@/lib/auth";
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

// entity keys
ok(normaliseEntityKey("ACME Steel Ltd.", "tr") === "acme steel|TR" && normaliseEntityKey("Acme-Steel Limited", "TR") === "acme steel|TR", "entity key drops legal suffixes and punctuation, keeps country");
ok(normaliseEntityKey("id:SUP-123") === "id:SUP-123", "an explicit id is kept");

// canonical URL and mirrors
ok(canonicalUrl("HTTPS://WWW.Example.com/a/b/?utm_source=x&b=2&a=1#frag") === "https://example.com/a/b?a=1&b=2", "canonical url: lower host, no www, no utm, no fragment, no trailing slash, sorted query");
ok(canonicalUrl("ftp://x.com/a") === "" && canonicalUrl("not a url") === "", "non-http input is not a url");
ok(isMirror({ url: "http://www.acme.com/products?utm_campaign=1" }, { url: "https://acme.com/products/" }), "same host+path is one source");
ok(!isMirror({ url: "https://acme.com/products" }, { url: "https://acme.com/about" }), "different paths are different sources");
ok(isMirror({ url: "https://a.com/x", doc_hash: "h1" }, { url: "https://b.org/y", doc_hash: "h1" }), "same document hash on two hosts is one source");
ok(countIndependent([{ url: "https://acme.com/p" }, { url: "http://www.acme.com/p/" }, { url: "https://registry.gov/acme" }, { doc_hash: "h1", url: "https://mirror1.com/d" }, { doc_hash: "h1", url: "https://mirror2.com/d" }]) === 3, "mirrored copies count once: 5 pieces of evidence, 3 independent sources");

// fixtures
const d = (s: string) => new Date(s);
const base = (o: Partial<Assertion> & { id: string }): Assertion => ({ ws: "acme", entity_kind: "supplier", entity_key: "acme steel|TR", property: "supplies", value: "steel pipes", unit: "", status: "observed",
  evidence: { url: "https://acme.com/products" }, independent_sources: 1, review_method: "web check, model agent", reviewed_at: "2026-01-01", reviewed_by: "model", supersedes: "", expires: "", created: "2026-01-01T00:00:00.000Z", ...o });

// resolve: human over model, latest wins
const r1 = base({ id: "m1", created: "2026-01-01T00:00:00.000Z" });
const r2 = base({ id: "m2", created: "2026-02-01T00:00:00.000Z", status: "inferred" });
const r3 = base({ id: "h1", created: "2026-01-15T00:00:00.000Z", review_method: "human entry", reviewed_by: "a@x.com", status: "observed" });
let res = resolve([r1, r2, r3]);
ok(res.length === 1 && res[0].id === "h1", "human review outranks a later model version of the same claim");
res = resolve([r1, r2]);
ok(res.length === 1 && res[0].id === "m2", "among model versions the latest wins");
const other = base({ id: "o1", property: "website", value: "https://acme.com" });
ok(resolve([r1, r2, r3, other]).length === 2, "different properties resolve separately");

// quarantine supersedes one claim and leaves the rest of the entity alone
const q = quarantine([r3, other], "h1", "catalogue page lists pipes only as a trader", "b@x.com", "disputed", d("2026-03-01T10:00:00Z"));
ok(!!q && q.supersedes === "h1" && q.status === "disputed" && String(q.evidence.reason).includes("trader") && q.review_method === "human quarantine" && q.reviewed_by === "b@x.com", "quarantine builds a superseding disputed row with the reason");
ok(!!q && q.evidence.url === "https://acme.com/products" && q.entity_key === "acme steel|TR" && q.value === "steel pipes", "the quarantined row keeps the original evidence and identity");
const after = resolve([r3, other, q!]);
ok(after.length === 2 && after.find((x) => x.property === "supplies")?.status === "disputed" && after.find((x) => x.property === "website")?.status === "observed", "after quarantine the claim reads as disputed and the entity's other property is untouched");
ok(r3.status === "observed", "stored rows are never mutated");
ok(quarantine([r3], "nope", "x", "b@x.com") === null, "quarantine of an unknown id returns null");
const rej = quarantine([r3, other, q!], q!.id, "confirmed wrong", "b@x.com", "rejected");
ok(resolve([r3, other, q!, rej!]).find((x) => x.property === "supplies")?.status === "rejected", "a rejection can supersede a dispute");

// expiry on read
const e1 = base({ id: "e1", expires: "2026-06-30" });
const e2 = base({ id: "e2", property: "legal_id", value: "123", expires: "2026-12-31" });
const e3 = base({ id: "e3", property: "export_to", value: "IL", status: "rejected", expires: "2026-06-30" });
const ex = expire([e1, e2, e3], d("2026-07-01T00:00:00Z"));
ok(ex[0].status === "expired" && ex[1].status === "observed" && ex[2].status === "rejected", "rows past expiry read as expired; rejected rows stay rejected");
ok(e1.status === "observed", "expiry never mutates the stored row");
ok(expire([e1], d("2026-06-30T23:00:00Z"))[0].status === "observed", "a row expires only after its date");

// workspace isolation
const priv = base({ id: "p1", ws: "acme" });
const pub = base({ id: "p2", ws: PUBLIC_WS, property: "website", value: "https://acme.com" });
const legacy = base({ id: "p3", ws: "", property: "legal_id", value: "9" });
ok(visibleTo([priv, pub, legacy], "acme").map((x) => x.id).join() === "p1,p2", "a workspace sees its own rows and public rows");
ok(visibleTo([priv, pub, legacy], "other").map((x) => x.id).join() === "p2", "another workspace never sees private rows");
ok(visibleTo([priv, pub, legacy], DEFAULT_WS).map((x) => x.id).join() === "p2,p3", "rows without a ws belong to the original workspace");
ok(filterRows([priv, pub], { property: "website" }).length === 1 && filterRows([priv, pub], { status: "rejected" }).length === 0, "filters by property and status");

// serialisation round trip
const mk = makeAssertion({ ws: "acme", entity_kind: "supplier", entity_key: "acme steel|TR", property: "capacity", value: "50000", unit: "t/y", status: "observed",
  evidence: { url: "https://WWW.acme.com/about/?utm_source=li", excerpt: "annual capacity of 50,000 tons", publisher: "Acme website", published: "2025-05-01" }, review_method: "human entry", reviewed_by: "a@x.com", now: d("2026-03-01T00:00:00Z") });
ok(mk.evidence.url === "https://acme.com/about" && mk.evidence.url_raw === "https://WWW.acme.com/about/?utm_source=li" && mk.independent_sources === 1 && mk.evidence.collected === "2026-03-01", "makeAssertion canonicalises the url and keeps the raw one");
const row = toRow(mk);
ok(row.length === 16 && typeof row[8] === "string" && JSON.parse(String(row[8])).excerpt === "annual capacity of 50,000 tons", "16 columns with evidence as JSON");
const back = fromRow(row);
ok(!!back && back.id === mk.id && back.unit === "t/y" && back.evidence.publisher === "Acme website" && back.status === "observed", "a row survives the round trip");
ok(fromRow([...row.slice(0, 8), "{not json", ...row.slice(9)])?.evidence !== undefined && fromGrid([["id", "ws"], row.map(String)]).length === 1, "bad evidence JSON does not crash; the header row is skipped");

// import of Verified capabilities
const grid = [
  ["supplier", "country", "product", "label", "evidence_url", "evidence_note", "checked", "method", "source_query"],
  ["Acme Steel Ltd", "TR", "steel pipes", "yes", "https://www.acme.com/products/", "Product page lists seamless pipes", "2026-02-10", "web check, model agent (not human)", "steel pipes"],
  ["Acme Steel Ltd", "TR", "diesel generators", "related", "https://acme.com/products", "Only gensets housings", "2026-02-11", "web check, model agent (not human)", "diesel generators"],
  ["Beta Co", "IL", "rice", "no", "user report", "reported as the wrong product by a user", "2026-02-12", "human report (x@y.com)", "rice"],
  ["Gamma", "EG", "cement", "unknown", "", "source not confirmed by the search", "2026-02-13", "web check, model agent (not human)", "cement"],
  ["", "EG", "cement", "yes", "", "", "", "", ""],
];
const imp = assertionsFromVerifiedCaps(grid);
ok(imp.length === 3, "unknown and empty rows are not imported");
ok(imp[0].status === "observed" && imp[0].property === "supplies" && imp[0].value === "steel pipes" && imp[0].entity_key === "acme steel|TR" && imp[0].ws === PUBLIC_WS && imp[0].evidence.url === "https://acme.com/products" && imp[0].reviewed_at === "2026-02-10", "yes -> observed supplies, public, canonical url, checked date kept");
ok(imp[1].status === "inferred" && imp[1].review_method === "web check, model agent" && imp[1].reviewed_by === "model", "related -> inferred, model review");
ok(imp[2].status === "rejected" && /^human/.test(imp[2].review_method) && imp[2].reviewed_by === "x@y.com" && imp[2].independent_sources === 0, "no -> rejected, human review kept, a user report is not a source");
ok(assertionsFromVerifiedCaps(grid).map((x) => x.id).join() === imp.map((x) => x.id).join() && imp[0].id !== imp[1].id, "import ids are stable content hashes");
const resolved = resolve(imp);
ok(resolved.length === 3 && resolved.find((x) => x.value === "steel pipes")?.status === "observed", "imported rows resolve one per claim");

console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
