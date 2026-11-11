// Client intake and targeting checks (spec phase 6). No network, no model: fixtures are generated here and the
// model, fetch, DNS and storage are fakes.
// Run: npx --yes esbuild@0.24.0 tests/dossier.test.ts --bundle --platform=node --format=cjs --alias:@=. --outfile=<scratch>/dossier.js && node <scratch>/dossier.js
import { deflateRawSync, deflateSync } from "zlib";
import { extractPdf, extractPptx, extractDocument } from "@/lib/docextract";
import { crawlSite, robotsAllows, privateAddress } from "@/lib/sitecrawl";
import {
  applyPatch, clientsIn, codeContradictions, dossierRowsFor, groundedIn, ingest, loadDossier, newDossier, outreachClaims, packJson,
  prioritizeQuestions, saveDossier, unpackJson, validateExtraction, type Dossier, type Store,
} from "@/lib/dossier";
import { classifyStage, discoverProspects, latestProspects, prospectId, prospectRowsFor, validateProfiles, type Profile } from "@/lib/targeting";

const ADMIN = { email: "rev@x.com", role: "admin" };  // approving a claim needs an admin or the client's representative
let fail = 0;
const ok = (c: boolean, m: string) => { console.log(`${c ? "ok  " : "FAIL"} ${m}`); if (!c) fail++; };

// ---------------------------------------------------------------- fixtures
function crc32(b: Buffer) { let c = ~0; for (const x of b) { c ^= x; for (let k = 0; k < 8; k++) c = (c >>> 1) ^ (0xedb88320 & -(c & 1)); } return ~c >>> 0; }
function zip(files: Record<string, string>): Buffer {
  const locals: Buffer[] = [], central: Buffer[] = [];
  let off = 0;
  for (const [name, text] of Object.entries(files)) {
    const raw = Buffer.from(text, "utf-8"), data = deflateRawSync(raw), nm = Buffer.from(name);
    const lh = Buffer.alloc(30); lh.writeUInt32LE(0x04034b50, 0); lh.writeUInt16LE(20, 4); lh.writeUInt16LE(8, 8); lh.writeUInt32LE(crc32(raw), 14); lh.writeUInt32LE(data.length, 18); lh.writeUInt32LE(raw.length, 22); lh.writeUInt16LE(nm.length, 26);
    const ch = Buffer.alloc(46); ch.writeUInt32LE(0x02014b50, 0); ch.writeUInt16LE(20, 4); ch.writeUInt16LE(20, 6); ch.writeUInt16LE(8, 10); ch.writeUInt32LE(crc32(raw), 16); ch.writeUInt32LE(data.length, 20); ch.writeUInt32LE(raw.length, 24); ch.writeUInt16LE(nm.length, 28); ch.writeUInt32LE(off, 42);
    locals.push(lh, nm, data); central.push(ch, nm); off += 30 + nm.length + data.length;
  }
  const cd = Buffer.concat(central), end = Buffer.alloc(22);
  end.writeUInt32LE(0x06054b50, 0); end.writeUInt16LE(central.length / 2, 8); end.writeUInt16LE(central.length / 2, 10); end.writeUInt32LE(cd.length, 12); end.writeUInt32LE(off, 16);
  return Buffer.concat([...locals, cd, end]);
}
const slide = (paras: string[], pic = false) => `<?xml version="1.0"?><p:sld xmlns:a="a" xmlns:p="p"><p:cSld><p:spTree>${pic ? "<p:pic/>" : ""}<p:sp><p:txBody>${paras.map((t) => `<a:p><a:r><a:t>${t}</a:t></a:r></a:p>`).join("")}</p:txBody></p:sp></p:spTree></p:cSld></p:sld>`;
const pptx = zip({
  "[Content_Types].xml": "<Types/>",
  // presentation order is slide2.xml first, then slide1.xml, then slide3.xml (file numbering is not the order)
  "ppt/presentation.xml": `<p:presentation xmlns:p="p" xmlns:r="r"><p:sldIdLst><p:sldId id="256" r:id="rId3"/><p:sldId id="257" r:id="rId2"/><p:sldId id="258" r:id="rId4"/></p:sldIdLst></p:presentation>`,
  "ppt/_rels/presentation.xml.rels": `<Relationships><Relationship Id="rId2" Type="slide" Target="slides/slide1.xml"/><Relationship Id="rId3" Type="slide" Target="slides/slide2.xml"/><Relationship Id="rId4" Type="slide" Target="slides/slide3.xml"/></Relationships>`,
  "ppt/slides/slide2.xml": slide(["AquaPure Ltd", "Containerized reverse osmosis units, 10-500 m3/day", "Founded 1998 &amp; ISO 9001 certified"]),
  "ppt/slides/_rels/slide2.xml.rels": `<Relationships><Relationship Id="rId1" Target="../notesSlides/notesSlide1.xml"/></Relationships>`,
  "ppt/notesSlides/notesSlide1.xml": slide(["Internal: target margin 30% on export deals"]),
  "ppt/slides/slide1.xml": slide(["Our customers", "Mekorot", "IDE", "Veolia", "Suez"]),
  "ppt/slides/slide3.xml": slide([], true),
});

function pdf(pages: string[], extra: Record<number, string> = {}): Buffer {
  // objects: 1 catalog, 2 pages, 3 font, 4.. page + content pairs
  const objs: string[] = [], bin: Buffer[] = [];
  const kids = pages.map((_, i) => `${4 + i * 2} 0 R`).join(" ");
  objs[1] = "<< /Type /Catalog /Pages 2 0 R >>";
  objs[2] = `<< /Type /Pages /Kids [${kids}] /Count ${pages.length} /Resources << /Font << /F1 3 0 R >> >> >>`;
  objs[3] = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>";
  pages.forEach((c, i) => { objs[4 + i * 2] = `<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents ${5 + i * 2} 0 R >>`; });
  const parts: Buffer[] = [Buffer.from("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n", "latin1")];
  const all: Record<number, Buffer | string> = { ...objs.reduce((m, v, i) => (v ? { ...m, [i]: v } : m), {}), ...extra };
  pages.forEach((c, i) => { const z = deflateSync(Buffer.from(c, "latin1")); all[5 + i * 2] = Buffer.concat([Buffer.from(`<< /Length ${z.length} /Filter /FlateDecode >>\nstream\n`), z, Buffer.from("\nendstream")]); });
  for (const [n, v] of Object.entries(all)) parts.push(Buffer.from(`${n} 0 obj\n`), Buffer.isBuffer(v) ? v : Buffer.from(v, "latin1"), Buffer.from("\nendobj\n"));
  parts.push(Buffer.from(`trailer\n<< /Root 1 0 R /Size ${Object.keys(all).length + 1} >>\n%%EOF\n`));
  void bin;
  return Buffer.concat(parts);
}

// ---------------------------------------------------------------- 1. PPTX extraction
{
  const r = extractPptx(pptx);
  ok(r.segments[0]?.ref === "slide 1" && r.segments[0].text.includes("Containerized reverse osmosis"), "pptx: slides follow the presentation order, not the file numbering");
  ok(r.segments[0].text.includes("Founded 1998 & ISO 9001"), "pptx: XML entities are decoded");
  ok(r.segments.some((s) => s.ref === "slide 1 notes" && s.text.includes("margin 30%")), "pptx: speaker notes are kept under their own reference");
  ok(r.segments.some((s) => s.ref === "slide 2" && s.text.split("\n").length === 5), "pptx: one line per paragraph");
  ok(r.gaps.length === 1 && r.gaps[0].ref === "slide 3" && /image-only/.test(r.gaps[0].reason), "pptx: an image-only slide is a reported gap, not guessed");
  ok(extractPptx(Buffer.from("not a zip")).error === "not a zip file", "pptx: a non-zip input is refused");
  ok(extractDocument(pptx, "deck.pptx").kind === "pptx", "dispatcher routes .pptx");
}

// ---------------------------------------------------------------- 2. PDF extraction
{
  const doc = pdf([
    "BT /F1 12 Tf 72 720 Td (AquaPure RO plant 50 m3/day) Tj 0 -14 Td [(recovery ) -250 (75%)] TJ T* (Certified \\(ISO 9001\\)) Tj ET",
    "q 0 0 612 792 re f Q",  // a page with graphics only (a scan)
  ]);
  const r = extractPdf(doc);
  ok(r.segments.length === 1 && r.segments[0].ref === "page 1", "pdf: text page found by its page number");
  ok(/AquaPure RO plant 50 m3\/day/.test(r.segments[0].text) && /recovery\s+75%/.test(r.segments[0].text), "pdf: Tj and TJ text read from a FlateDecode stream");
  ok(r.segments[0].text.includes("Certified (ISO 9001)"), "pdf: escaped parentheses are decoded");
  ok(r.gaps.length === 1 && r.gaps[0].ref === "page 2" && /OCR/.test(r.gaps[0].reason), "pdf: a page without a text layer is a gap (OCR not run)");
  // Type0 font with a ToUnicode CMap (how most office and design tools embed fonts)
  const cmap = "/CIDInit /ProcSet findresource begin 12 dict begin begincmap 1 begincodespacerange <0000> <FFFF> endcodespacerange 2 beginbfchar <0001> <05E9> <0002> <05DC> endbfchar 1 beginbfrange <0010> <0012> <0041> endbfrange endcmap end end";
  const z = deflateSync(Buffer.from(cmap));
  const doc2 = pdf(["BT /F2 12 Tf 72 720 Td <000100020010001100120010> Tj <000100020010001100120010> Tj ET"], {
    2: "<< /Type /Pages /Kids [4 0 R] /Count 1 /Resources << /Font << /F2 9 0 R >> >> >>",
    9: "<< /Type /Font /Subtype /Type0 /BaseFont /X /Encoding /Identity-H /ToUnicode 10 0 R >>",
    10: Buffer.concat([Buffer.from(`<< /Length ${z.length} /Filter /FlateDecode >>\nstream\n`), z, Buffer.from("\nendstream")]) as unknown as string,
  });
  const r2 = extractPdf(doc2);
  ok(r2.segments[0]?.text === "שלABCAשלABCA", "pdf: two-byte codes are mapped through ToUnicode (bfchar and bfrange)");
  const enc = Buffer.from(doc.toString("latin1").replace("<< /Root 1 0 R", "<< /Root 1 0 R /Encrypt 99 0 R"), "latin1");
  ok(extractPdf(enc).error === "encrypted PDF", "pdf: an encrypted file is reported, not read");
  ok(extractDocument(Buffer.from("hello"), "x.pdf").error === "not a PDF file", "pdf: a non-PDF is refused");
}

// ---------------------------------------------------------------- 3. claim validation
const chunk = [{ ref: "slide 1", text: "Containerized reverse osmosis units, 10-500 m3/day\nFounded 1998, ISO 9001 certified\nUp to 40% lower energy use" },
  { ref: "slide 2", text: "Our customers\nMekorot\nIDE\nVeolia\nSuez" }, { ref: "slide 1 notes", text: "Internal: target margin 30% on export deals" }];
{
  const raw = { claims: [
    { field: "products_services", value: "Containerized reverse osmosis units, 10-500 m3/day", source_ref: "Slide 1", type: "verified" },
    { field: "certifications", value: "ISO 9001 certified" },                                                  // no source_ref
    { field: "certifications", value: "ISO 9001 certified", source_ref: "" },                                  // empty source_ref
    { field: "certifications", value: "ISO 14001 certified", source_ref: "slide 1" },                          // number not in the source
    { field: "capabilities", value: "Desalination of seawater at 45,000 ppm", source_ref: "slide 1" },        // not in the source
    { field: "identity", value: "Founded 1998", source_ref: "page 7" },                                        // ref not in this document
    { field: "made_up", value: "x y z", source_ref: "slide 1" },                                               // unknown field
    { field: "differentiators", value: "Up to 40% lower energy use", source_ref: "slide 1" },                 // performance claim
    { field: "customers_partners", value: "Mekorot", source_ref: "slide 2" },                                  // logo list
    { field: "private_info", value: "target margin 30% on export deals", source_ref: "slide 1 notes" },
  ], contradictions: [{ note: "x", source_refs: ["page 99"] }], questions: [{ question: "Which feedwater salinity can the units treat?", changes_target_market: true, field: "capabilities" }] };
  const v = validateExtraction(raw, chunk, { doc: "deck.pptx", by: "a@x.com" });
  ok(v.claims.length === 4, `four claims kept (got ${v.claims.length})`);
  ok(v.rejected.filter((r) => r.reason === "no source_ref").length === 2, "claims without a source_ref are rejected");
  ok(v.rejected.some((r) => /not found in slide 1/.test(r.reason)) && v.rejected.filter((r) => /not found/.test(r.reason)).length === 2, "claims the cited slide does not hold are rejected");
  ok(v.rejected.some((r) => /not a page, slide or URL of this document/.test(r.reason)), "a source_ref outside the document is rejected");
  ok(v.rejected.some((r) => /unknown field/.test(r.reason)), "an unknown field is rejected");
  ok(v.claims.every((c) => c.type === "client assertion"), "every extracted claim is a client assertion (the model cannot mark it verified)");
  ok(v.claims[0].source_ref === "slide 1", "source_ref is normalised to the document's own label");
  ok(v.claims.find((c) => c.field === "differentiators")!.flags.some((f) => f.startsWith("unsupported performance")), "a performance claim is flagged as unsupported");
  ok(v.claims.find((c) => c.field === "customers_partners")!.flags.some((f) => f.startsWith("ambiguous customer logo")), "a name on a logo slide is flagged as ambiguous");
  ok(v.claims.find((c) => c.field === "private_info")!.private, "private information and speaker notes are private");
  ok(v.contradictions.length === 0 && v.rejected.some((r) => /contradiction/.test(r.reason)), "a contradiction citing no valid source is rejected");
  ok(v.questions.length === 1 && v.questions[0].changes_target_market, "questions are kept with their target-market flag");
  ok(validateExtraction({ nonsense: true }, chunk, { doc: "d", by: "a" }).rejected[0].reason === "model output had no claims array", "malformed model output is rejected as a whole");
  ok(groundedIn("installation in 12 countries", "Installed in 12 countries") && !groundedIn("installed in 14 countries", "Installed in 12 countries"), "grounding needs every number and most words");
}

// ---------------------------------------------------------------- 4. dossier edits, status and contradictions
{
  const d = newDossier({ name: "AquaPure", domains: ["https://www.aquapure.example/about"] }, "a@x.com");
  ok(d.identity.official_domains[0] === "aquapure.example" && /^CL-[A-Z0-9]+$/.test(d.client_id), "new dossier: domain normalised, id issued");
  const v = validateExtraction({ claims: [
    { field: "products_services", value: "Containerized reverse osmosis units, 10-500 m3/day", source_ref: "slide 1" },
    { field: "differentiators", value: "Up to 40% lower energy use", source_ref: "slide 1" },
    { field: "identity", value: "Founded 1998", source_ref: "slide 1" } ] }, chunk, { doc: "deck", by: "a" });
  d.claims = v.claims;
  d.claims.push({ ...v.claims[2], id: "K2", value: "Founded 2003", source_ref: "https://aquapure.example/about" });
  ok(codeContradictions(d.claims).length === 1, "code finds two sources giving different founding years");
  const perf = d.claims.find((c) => c.field === "differentiators")!;
  let r = applyPatch(d, { update_claims: [{ id: perf.id, approved: true }] }, "rev@x.com", ADMIN);
  ok(r.ok && r.errors.some((e) => /independent source/.test(e)) && !r.dossier.claims.find((c) => c.id === perf.id)!.approved, "a flagged performance claim cannot be approved without an independent source");
  r = applyPatch(d, { update_claims: [{ id: perf.id, verified_source: "https://shop.aquapure.example/test" }] }, "rev@x.com");
  ok(r.ok && r.errors.some((e) => /own site cannot verify/.test(e)), "the client's own domain cannot verify its own claim");
  r = applyPatch(d, { update_claims: [{ id: perf.id, verified_source: "https://lab.example.org/report-17" }] }, "rev@x.com");
  ok(r.ok && r.dossier.claims.find((c) => c.id === perf.id)!.type === "verified fact", "an independent URL makes a verified fact");
  const blocked = applyPatch(d, { status: "reviewed" }, "rev@x.com");
  ok(!blocked.ok && (blocked.blockers || []).some((b) => /contradiction/.test(b)), "review is blocked while a contradiction is open");
  const cid = codeContradictions(d.claims)[0].id;
  const rev = applyPatch(d, { resolve_contradictions: [{ id: cid, resolution: "2003 is the incorporation; 1998 the founder's first company" }], status: "reviewed" }, "rev@x.com");
  ok(rev.ok && rev.dossier.status === "reviewed", "after resolving it the dossier can be reviewed");
  const act0 = rev.ok ? applyPatch(rev.dossier, { status: "active" }, "rev@x.com") : null;
  ok(!!act0 && !act0.ok && /approve at least one claim/.test(act0.error), "activation needs at least one approved claim");
  const prod = d.claims.find((c) => c.field === "products_services")!;
  const appr = rev.ok ? applyPatch({ ...rev.dossier, status: "reviewed" }, { update_claims: [{ id: prod.id, approved: true }] }, "rev@x.com", ADMIN) : null;
  ok(!!appr && appr.ok && appr.status_reset && appr.dossier.status === "draft", "a content edit on a reviewed dossier sends it back to draft");
  const direct = applyPatch(d, { status: "active" }, "rev@x.com");
  ok(!direct.ok, "a draft cannot jump to active");
  if (appr && appr.ok) {
    const re = applyPatch(appr.dossier, { status: "reviewed" }, "rev@x.com");
    const act = re.ok ? applyPatch(re.dossier, { status: "active" }, "rev@x.com") : null;
    ok(!!act && act.ok && act.dossier.status === "active" && outreachClaims(act.dossier).length === 1, "draft -> reviewed -> active; outreach sees approved claims only");
  }
  const qs = prioritizeQuestions(d);
  ok(qs.length > 0 && qs[0].changes_target_market && qs.findIndex((q) => !q.changes_target_market) > qs.findIndex((q) => q.changes_target_market), "questions that change the target market come first");
  const big = { ...d, claims: Array.from({ length: 400 }, (_, i) => ({ ...d.claims[0], id: `K${i}`, value: `${d.claims[0].value} variant ${i}` })) };
  const packed = packJson(big);
  ok(packed.length <= 45000 && unpackJson<Dossier>(packed)!.claims.length === 400, "a large dossier is compressed to fit one cell");
}

// ---------------------------------------------------------------- 5. workspace and client isolation
const memStore = (rows: string[][] = []): Store & { rows: string[][] } => ({ rows, read: async () => rows, append: async (r) => { rows.push(r.map(String)); } });
(async () => {
  const store = memStore([["ws", "client_id", "version", "status", "json", "updated", "by"]]);
  const a = newDossier({ name: "Alpha Water" }, "a@acme"), b = newDossier({ name: "Beta Pumps" }, "b@acme"), c = newDossier({ name: "Gamma Other" }, "c@other");
  a.private_notes = ["Alpha price list: USD 120,000 per unit"];
  await saveDossier("acme", a, 1, "a", store); await saveDossier("acme", b, 1, "b", store); await saveDossier("other", c, 1, "c", store);
  await saveDossier("acme", { ...a, name: "Alpha Water Ltd" }, 2, "a", store);
  ok(dossierRowsFor(store.rows, "acme", a.client_id).length === 2 && dossierRowsFor(store.rows, "other", a.client_id).length === 0, "storage filter: rows are read by workspace AND client id");
  ok((await loadDossier("acme", a.client_id, store))?.dossier.name === "Alpha Water Ltd", "the latest version is served");
  ok((await loadDossier("other", a.client_id, store)) === null, "a client id from another workspace is not found (404)");
  ok((await loadDossier("acme", c.client_id, store)) === null, "and the other way round");
  ok((await loadDossier("acme", "../../x", store)) === null, "a malformed client id is not found");
  const listA = clientsIn(store.rows, "acme");
  ok(listA.length === 2 && listA.every((x) => x.client_id !== c.client_id) && !JSON.stringify(listA).includes("USD 120,000"), "the client list holds only this workspace's clients and no dossier content");
  // the model never sees another client's material, and cached answers are not shared between clients
  const prompts: string[] = [];
  const model = async (p: string) => { prompts.push(p); return JSON.stringify({ claims: [{ field: "products_services", value: "Containerized reverse osmosis units, 10-500 m3/day", source_ref: "slide 1" }], contradictions: [], questions: [] }); };
  const ra = await ingest("acme", a.client_id, { file: pptx, filename: "deck.pptx" }, "a", { model, store });
  const rb = await ingest("acme", b.client_id, { file: pptx, filename: "deck.pptx" }, "b", { model, store });
  ok(ra.ok && rb.ok && prompts.length === 2, "the same document for two clients is analysed separately (no shared cache)");
  ok(!prompts[1].includes("Alpha") && !prompts[0].includes("Beta") && !prompts.some((p) => p.includes("USD 120,000")), "a prompt holds only its own client's name and material, never private notes");
  const again = await ingest("acme", a.client_id, { file: pptx, filename: "deck.pptx" }, "a", { model, store });
  ok(again.ok && again.duplicate === true && prompts.length === 2, "re-sending the same document is recognised by content hash");
  ok(ra.ok && ra.added === 1 && ra.gaps.some((g) => g.ref === "slide 3"), "ingest stores validated claims and reports gaps");
  const cross = await ingest("other", a.client_id, { file: pptx, filename: "deck.pptx" }, "x", { model, store });
  ok(!cross.ok && cross.status === 404, "ingest into another workspace's client returns 404");
  ok(prospectId("acme", a.client_id, "City Water Co", "ISR", "end_user") !== prospectId("acme", b.client_id, "City Water Co", "ISR", "end_user"), "prospect ids are per client");
  const prow = [["acme", a.client_id, "P-1", "active_signal", JSON.stringify({ prospect_id: "P-1", evidence: [], stage: "active_signal" }), "t"],
    ["acme", b.client_id, "P-2", "structural_fit", JSON.stringify({ prospect_id: "P-2", evidence: [], stage: "structural_fit" }), "t"],
    ["other", a.client_id, "P-3", "structural_fit", JSON.stringify({ prospect_id: "P-3", evidence: [], stage: "structural_fit" }), "t"],
    ["acme", a.client_id, "P-1", "evidenced_need", JSON.stringify({ prospect_id: "P-1", evidence: [], stage: "evidenced_need" }), "t2"]];
  const pa = latestProspects(prospectRowsFor(prow, "acme", a.client_id));
  ok(pa.length === 1 && pa[0].prospect_id === "P-1" && pa[0].stage === "evidenced_need", "prospect filter: own workspace and client only, last row wins");

  // ---------------------------------------------------------------- 6. crawl
  const site: Record<string, [number, string, string?]> = {
    "https://aqua.example/robots.txt": [200, "User-agent: *\nDisallow: /internal\n"],
    "https://aqua.example": [200, `<html><title>AquaPure</title><body><script>ignore()</script><p>We build containerized reverse osmosis units for industry and municipalities across Africa and Asia.</p>
      <a href="/products">Products</a><a href="/about-us">About</a><a href="/internal/prices">x</a><a href="/login">Log in</a><a href="https://evil.example/x">x</a><a href="/brochure.pdf">pdf</a><a href="/products?utm_source=x">dup</a><a href="/copy">copy</a></body></html>`],
    "https://aqua.example/products": [200, "<html><body><h1>Products</h1><p>RO-50 and RO-500 containerized systems, 10 to 500 cubic metres per day, brackish and sea water models.</p></body></html>"],
    "https://aqua.example/about-us": [301, "", "https://www.aqua.example/about"],
    "https://www.aqua.example/about": [200, "<html><body><p>Founded 1998 in Haifa. ISO 9001 certified. Service partners in Kenya, Ghana and India support installations.</p></body></html>"],
    "https://aqua.example/copy": [200, "<html><body><h1>Products</h1><p>RO-50 and RO-500 containerized systems, 10 to 500 cubic metres per day, brackish and sea water models.</p></body></html>"],
  };
  const fetched: string[] = [];
  const fakeFetch = async (u: string) => { fetched.push(u); const x = site[u.replace(/\/$/, "")] || site[u]; if (!x) return new Response("nf", { status: 404 }); return new Response(x[1], { status: x[0], headers: { "content-type": u.endsWith(".txt") ? "text/plain" : "text/html", ...(x[2] ? { location: x[2] } : {}) } }); };
  const cr = await crawlSite("aqua.example", { fetch: fakeFetch as never, resolve: async () => ["93.184.216.34"] });
  ok(cr.pages.length === 3 && cr.pages[0].text.includes("reverse osmosis") && !cr.pages[0].text.includes("ignore()"), `crawl: home, products and about read as text, scripts dropped (got ${cr.pages.length})`);
  ok(!fetched.some((u) => u.includes("/internal") || u.includes("/login") || u.includes("evil.example") || u.endsWith(".pdf")), "crawl: robots.txt, login pages, other sites and files are skipped");
  ok(cr.skipped.some((s) => s.reason === "duplicate content"), "crawl: duplicate content is dropped by hash");
  ok(cr.pages.some((p) => p.url === "https://www.aqua.example/about"), "crawl: a redirect to www of the same site is followed");
  const priv = await crawlSite("http://intranet.example", { fetch: fakeFetch as never, resolve: async () => ["10.0.0.5"] });
  ok(!!priv.error && !priv.pages.length, "crawl: a host resolving to a private address is refused");
  ok(privateAddress("169.254.169.254") && privateAddress("127.0.0.1") && !privateAddress("8.8.8.8"), "private address guard");
  ok(!robotsAllows("User-agent: *\nDisallow: /\nAllow: /products", "/about") && robotsAllows("User-agent: *\nDisallow: /\nAllow: /products", "/products/ro"), "robots: longest rule wins");

  // ---------------------------------------------------------------- 7. targeting: profiles grounded, stages kept apart
  const dz = newDossier({ name: "AquaPure" }, "a");
  dz.claims = validateExtraction({ claims: [{ field: "products_services", value: "Containerized reverse osmosis units, 10-500 m3/day", source_ref: "slide 1" }] }, chunk, { doc: "d", by: "a" }).claims;
  dz.claims.push({ ...dz.claims[0], id: "KX1", field: "exclusions", value: "Mekorot" });
  const kid = dz.claims[0].id;
  const vp = validateProfiles({ profiles: [
    { category: "end_user", title: "Industrial plants with brackish feedwater", geographies: ["ISR", "Sub-Saharan Africa", "Mars"], search_terms: ["reverse osmosis", "desalination"], basis: [kid], buyer_function: "plant engineering / procurement",
      fit_parameters: [{ parameter: "feedwater salinity", client_range: "brackish", basis: "K-made-up" }, { parameter: "capacity", client_range: "10-500 m3/day", basis: kid }] },
    { category: "distributor", title: "Water treatment distributors", search_terms: ["water treatment"], basis: [kid] },
    { category: "end_user", title: "Ungrounded", search_terms: ["pumps"], basis: ["K-NOPE"] },
    { category: "astronaut", title: "x", search_terms: ["x"], basis: [kid] } ] }, dz);
  ok(vp.profiles.length === 2 && vp.rejected.length === 2, "profiles without a dossier basis or with an unknown category are rejected");
  ok(vp.profiles[0].geographies.join() === "ISR,Sub-Saharan Africa", "geographies are ISO3 codes or known regions only");
  ok(/unknown - ask client/.test(vp.profiles[0].fit_parameters[0].client_range) && vp.profiles[0].fit_parameters[1].basis === kid, "a fit parameter not backed by a claim becomes a question for the client");
  const profiles: Profile[] = vp.profiles;
  const future = new Date(Date.now() + 20 * 86400e3).toISOString().slice(0, 10), past = new Date(Date.now() - 20 * 86400e3).toISOString().slice(0, 10);
  const recent = new Date(Date.now() - 200 * 86400e3).toISOString().slice(0, 10), old = new Date(Date.now() - 6 * 365 * 86400e3).toISOString().slice(0, 10);
  const found = discoverProspects("acme", dz, profiles, {
    tenders: [
      { id: "T1", title_en: "Supply of reverse osmosis plant 200 m3/day", buyer: "Negev Water Corp", country: "ISR", region: "Israel", stage: "tender", deadline: future, contact: "tenders@negev.example", link: "https://t/1" },
      { id: "T2", title_en: "Desalination project phase 2 (planned)", buyer: "Kenya Coast Water", country: "KEN", region: "Sub-Saharan Africa", stage: "planned", deadline: "" },
      { id: "T3", title_en: "Reverse osmosis membranes", buyer: "Closed Buyer Ltd", country: "ISR", region: "Israel", stage: "tender", deadline: past },
      { id: "T4", title_en: "Reverse osmosis unit", buyer: "Mekorot", country: "ISR", region: "Israel", stage: "tender", deadline: future },
      { id: "T5", title_en: "Reverse osmosis unit", buyer: "Far Away Co", country: "BRA", region: "Latin America", stage: "tender", deadline: future },
      { id: "T6", title_en: "Office furniture", buyer: "Negev Water Corp", country: "ISR", region: "Israel", stage: "tender", deadline: future },
    ],
    awards: [
      { published: recent, country: "ISR", buyer: "Haifa Chemicals Plant", title: "Reverse osmosis system maintenance", winners: "Filter Distributors Ltd", winner_country: "ISR", link: "https://a/1" },
      { published: old, country: "ISR", buyer: "Old Buyer Works", title: "Reverse osmosis skid", link: "https://a/2" },
    ],
    suppliers: { [profiles[1].id]: [
      { supplier: "Hydro Traders", country: "KEN", region: "Sub-Saharan Africa", kind: "trader", type: "distributor", products: "water treatment chemicals and equipment" },
      { supplier: "Membrane Maker SA", country: "ESP", kind: "maker", type: "manufacturer", products: "water treatment membranes" },
    ] },
  });
  const P = (n: string) => found.prospects.find((p) => p.entity === n);
  ok(P("Negev Water Corp")?.stage === "active_signal" && /notice contact/.test(P("Negev Water Corp")!.contact_channel), "an open tender for the category is an active buying signal, with the notice contact as the channel");
  ok(P("Negev Water Corp")!.evidence.length === 1, "a tender outside the category adds no evidence (office furniture)");
  ok(P("Kenya Coast Water")?.stage === "evidenced_need", "a planned project is evidenced need, not purchasing intent");
  ok(P("Haifa Chemicals Plant")?.stage === "evidenced_need" && P("Haifa Chemicals Plant")!.contact_channel === "none", "a recent past purchase is evidenced need; no contact is invented");
  ok(P("Old Buyer Works")?.stage === "structural_fit", "a purchase older than three years is structural fit only");
  ok(P("Closed Buyer Ltd")?.stage === "structural_fit", "a closed tender is not an active signal");
  ok(P("Hydro Traders")?.stage === "structural_fit" && P("Hydro Traders")!.role === "distributor", "a supplier-universe record (industry membership) is structural fit only");
  ok(!P("Membrane Maker SA") && found.competitors_skipped === 1, "a maker of the same category is skipped as a likely competitor");
  ok(!P("Mekorot") && found.excluded.some((x) => x.entity === "Mekorot"), "an entity the client excluded is never a prospect");
  ok(!P("Far Away Co"), "a buyer outside the profile's geography is left out");
  ok(found.prospects.every((p) => p.next_action && p.buying_stage && p.timing && p.decision_maker_function !== undefined), "every prospect carries buying stage, timing, decision function and next action");
  ok(classifyStage([{ kind: "supplier_record", date: "" }, { kind: "award_winner", date: recent }]) === "structural_fit", "industry membership and award wins alone stay structural fit");
  ok(classifyStage([{ kind: "planned_project", date: "" }, { kind: "open_tender", date: future }]) === "active_signal", "an open tender outranks other evidence");
  ok(found.prospects[0].stage === "active_signal", "prospects are ordered active, then evidenced need, then structural fit");

  console.log(fail ? `${fail} FAILED` : "all passed"); process.exit(fail ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
