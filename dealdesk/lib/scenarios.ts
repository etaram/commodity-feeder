// ---- 20 deal scenarios, end to end over the app's own routes (read-only): finding an opportunity, finding who can
// supply it, pricing it, reading the country, and the execution options. Each scenario states what must be true and
// reports pass / fail with the reason, so a break between two parts of the system shows up as a named failure.
type Res = { status: number; ms: number; j: Record<string, unknown> | null };
type Scn = { id: number; stage: string; name: string; run: (call: (path: string, body?: unknown) => Promise<Res>) => Promise<string[]> };
const grid = (r: Res) => { const v = (r.j?.values || []) as string[][]; const h = (v[0] || []) as string[]; return v.slice(1).map((row) => Object.fromEntries(h.map((k, i) => [k, String(row[i] ?? "")]))) as Record<string, string>[]; };
const okRes = (r: Res, max = 30000) => [r.status !== 200 ? `status ${r.status}` : "", r.j?.ok === false ? `error: ${String(r.j?.error).slice(0, 120)}` : "", r.ms > max ? `slow: ${r.ms} ms` : ""].filter(Boolean);
const tSearch = (q: string, cty = "") => ({ kind: "t", values: [["\\b" + q, "country", cty], ["", "min value", ""], ["", "max value", ""], ["", "", ""], [0, "", ""], [2000, "fit", ""]] });
const cSearch = (q: string, cty = "") => ({ kind: "c", values: [["\\b" + q], [""], [cty], [""], [0], [""], [""]] });
const share = (rows: Record<string, string>[], n: number, f: (r: Record<string, string>) => boolean) => rows.slice(0, n).filter(f).length;
const txt = (r: Record<string, string>) => `${r.supplier} ${r.products} ${r.commodities} ${r.hs_names} ${r.industries} ${r.supplied}`.toLowerCase();
const past = (d: string) => { const t = Date.parse(/^\d{4}-\d{2}-\d{2}/.test(d) ? d.slice(0, 10) : d); return isFinite(t) && t > Date.UTC(1990, 0, 1) && t < Date.now() - 36 * 3600e3; };
const need = (cond: boolean, msg: string) => (cond ? [] : [msg]);
const SCN: Scn[] = [
  { id: 1, stage: "opportunity", name: "tender search in English: solar", run: async (c) => { const r = await c("/api/panel/search", tSearch("solar")); const g = grid(r);
    return [...okRes(r), ...need(g.length >= 5, `only ${g.length} tenders`), ...need(share(g, 20, (x) => /solar|photovolt|\bpv\b/i.test(`${x.title_en} ${x.title_original} ${x.commodity} ${x.sector} ${x.summary_en}`)) >= Math.min(20, g.length) * 0.8, "most of the top 20 do not name solar"), ...need(!g.some((x) => past(x.deadline)), "a closed tender is listed")]; } },
  { id: 2, stage: "opportunity", name: "tender search in Hebrew: דאטה סנטר", run: async (c) => { const r = await c("/api/panel/search", tSearch("דאטה סנטר")); return [...okRes(r, 20000), ...need(grid(r).length >= 1, "no tenders")]; } },
  { id: 3, stage: "opportunity", name: "tender search with a country filter: road, Kenya", run: async (c) => { const r = await c("/api/panel/search", tSearch("road", "KEN")); const g = grid(r);
    return [...okRes(r), ...need(g.every((x) => x.country === "KEN"), "a tender from another country passed the filter")]; } },
  { id: 4, stage: "opportunity", name: "my tender list: open, with ids and deadlines", run: async (c) => { const r = await c("/api/panel/get", { key: "tenders" }); const g = grid(r);
    return [...okRes(r), ...need(g.length >= 100, `only ${g.length} rows`), ...need(g.every((x) => !!x.id), "a row without an id"), ...need(!g.some((x) => past(x.deadline)), "a closed tender is listed")]; } },
  { id: 5, stage: "opportunity", name: "tender search and tender list agree (an id found by search exists in the store)", run: async (c) => { const a = grid(await c("/api/panel/search", tSearch("transformer"))); const first = a[0];
    if (!first) return ["no tender for 'transformer'"]; const b = grid(await c("/api/panel/search", tSearch(String(first.title_en || "").split(" ").slice(0, 3).join(" "), first.country)));
    return need(b.some((x) => x.id === first.id), "the same tender is not found again by its own title and country"); } },
  { id: 6, stage: "suppliers", name: "companies: sidamo coffee producer", run: async (c) => { const r = await c("/api/panel/search", cSearch("sidamo coffee producer")); const g = grid(r);
    return [...okRes(r), ...need(g.length >= 10, `only ${g.length} companies`), ...need(share(g, 10, (x) => x.country === "ETH") >= 7, `only ${share(g, 10, (x) => x.country === "ETH")} of the top 10 are Ethiopian`), ...need(share(g, 10, (x) => /coffee/i.test(txt(x))) >= 9, "top 10 do not all name coffee"), ...(() => { const bad = g.slice(0, 30).findIndex((x) => /coffee (table|machine|maker)/i.test(txt(x)) && !/green coffee|coffee bean|arabica/i.test(txt(x))); return bad < 0 ? [] : [`a look-alike at rank ${bad + 1} (${g[bad].country}): ${txt(g[bad]).replace(String(g[bad].supplier).toLowerCase(), "").trim().slice(0, 200)}`]; })()]; } },
  { id: 7, stage: "suppliers", name: "companies: jasmine rice", run: async (c) => { const r = await c("/api/panel/search", cSearch("jasmine rice")); const g = grid(r);
    return [...okRes(r), ...need(share(g, 10, (x) => /jasmine|hom mali/i.test(txt(x))) >= 7, `only ${share(g, 10, (x) => /jasmine|hom mali/i.test(txt(x)))} of the top 10 name jasmine / hom mali`), ...need(share(g, 10, (x) => ["THA", "KHM", "VNM"].includes(x.country)) >= 7, "top 10 are not from the origin countries")]; } },
  { id: 8, stage: "suppliers", name: "companies in Hebrew: אורז יסמין gives the same as jasmine rice", run: async (c) => { const a = grid(await c("/api/panel/search", cSearch("jasmine rice"))), b = grid(await c("/api/panel/search", cSearch("אורז יסמין")));
    const same = a.slice(0, 10).filter((x) => b.slice(0, 10).some((y) => y.supplier === x.supplier)).length; return [...need(b.length >= 10, `only ${b.length} companies in Hebrew`), ...need(same >= 8, `only ${same} of the top 10 are the same in both languages`)]; } },
  { id: 9, stage: "suppliers", name: "companies: coffee table is furniture, not coffee", run: async (c) => { const r = await c("/api/panel/search", cSearch("coffee table")); const g = grid(r);
    return [...okRes(r), ...need(g.length === 0 || share(g, 10, (x) => /table/i.test(txt(x))) >= Math.min(10, g.length) * 0.8, "top results do not name a table")]; } },
  { id: 10, stage: "suppliers", name: "supplier match: power transformer", run: async (c) => { const r = await c("/api/panel/suppliers-for", { text: "power transformer", n: 15, strict: true }); const g = grid(r);
    return [...okRes(r), ...need(g.length >= 5, `only ${g.length}`), ...need(g.every((x) => !!x.match), "a result without a match verdict"), ...need(share(g, 5, (x) => /transform/i.test(txt(x))) >= 4, "top 5 do not name transformers"), ...need(!g.some((x) => x.match === "incompatible"), "an incompatible company is shown")]; } },
  { id: 11, stage: "suppliers", name: "supplier match: raw cashew nuts", run: async (c) => { const r = await c("/api/panel/suppliers-for", { text: "raw cashew nuts", n: 15, strict: true }); const g = grid(r);
    return [...okRes(r), ...need(share(g, 10, (x) => /cashew/i.test(txt(x))) >= 9, "top 10 do not all name cashew")]; } },
  { id: 12, stage: "suppliers", name: "producers before exporters: green coffee", run: async (c) => { const g = grid(await c("/api/panel/suppliers-for", { text: "green coffee", n: 40, strict: true })); const mk = g.findIndex((x) => x.kind === "maker"), tr = g.findIndex((x) => x.kind === "trader");
    return [...need(g.length >= 20, `only ${g.length}`), ...need(mk < 0 || tr < 0 || mk < tr, `the first trader (rank ${tr + 1}) is above the first producer (rank ${mk + 1})`)]; } },
  { id: 13, stage: "suppliers", name: "origin filter: robusta coffee from Vietnam", run: async (c) => { const g = grid(await c("/api/panel/suppliers-for", { text: "robusta coffee", n: 20, originCountry: "VNM" }));
    return [...need(g.length >= 3, `only ${g.length}`), ...need(g.every((x) => x.country === "VNM"), "a company from another country passed the origin filter")]; } },
  { id: 14, stage: "suppliers", name: "a product family is not mixed: frozen tuna does not return shrimp-only firms", run: async (c) => { const g = grid(await c("/api/panel/suppliers-for", { text: "frozen tuna", n: 15, strict: true }));
    return [...need(g.length >= 5, `only ${g.length}`), ...need(share(g, 10, (x) => /tuna|skipjack|yellowfin|thunnus|0303|1604/i.test(`${txt(x)} ${x.hs_codes}`)) >= 8, "top 10 do not name tuna")]; } },
  { id: 15, stage: "pricing", name: "coffee prices: fresh, positive, with a source", run: async (c) => { const r = await c("/api/panel/commodities?product=coffee&limit=80"); const it = ((r.j?.items || []) as Record<string, unknown>[]);
    const fresh = it.filter((i) => (Date.now() - Date.parse(String(i.date || i.timestamp || ""))) / 864e5 <= 45).length;
    return [...okRes(r), ...need(it.length >= 3, `only ${it.length} coffee prices`), ...need(fresh >= 2, `only ${fresh} coffee prices from the last 45 days`), ...need(it.every((i) => !(Number(i.price_usd) <= 0)), "a zero or negative price"), ...need(it.every((i) => !!(i.source || i.link)), "a price without a source")]; } },
  { id: 16, stage: "pricing", name: "coffee prices are coherent with each other (USD per tonne within one order of magnitude)", run: async (c) => { const it = (((await c("/api/panel/commodities?product=coffee&limit=200")).j?.items || []) as Record<string, unknown>[]).filter((i) => ["T1", "T2"].includes(String(i.source_tier)) && /green|arabica|robusta/i.test(`${i.product} ${i.commodity}`) && !/retail/i.test(String(i.grade))).map((i) => Number(i.price_usd_t)).filter((n) => n > 0);   // official and primary sources, green coffee, not retail
    return [...need(it.length >= 3, `only ${it.length} prices per tonne`), ...need(it.length < 3 || Math.max(...it) / Math.min(...it) < 12, `per-tonne prices spread ${Math.round(Math.max(...it) / Math.min(...it))}x (a unit error)`)]; } },
  { id: 17, stage: "pricing", name: "rice and sesame prices exist", run: async (c) => { const a = ((await c("/api/panel/commodities?product=rice&limit=40")).j?.items || []) as unknown[], b = ((await c("/api/panel/commodities?product=sesame&limit=40")).j?.items || []) as unknown[];
    return [...need(a.length >= 1, "no rice price"), ...need(b.length >= 1, "no sesame price")]; } },
  { id: 18, stage: "country", name: "country page: Ethiopia and Kenya load with content", run: async (c) => { const a = await c("/api/panel/country?c=ETH"), b = await c("/api/panel/country?c=KEN");
    return [...okRes(a), ...okRes(b), ...need(JSON.stringify(a.j || {}).length > 2000, "Ethiopia page is nearly empty"), ...need(JSON.stringify(b.j || {}).length > 2000, "Kenya page is nearly empty")]; } },
  { id: 19, stage: "execution", name: "financing and logistics options for an agri deal into Kenya", run: async (c) => { const f = await c("/api/panel/finance", { sector: "Agriculture & food", region: "Africa", buyerCountry: "KEN" }), l = await c("/api/panel/logistics", { sector: "Agriculture & food", region: "Africa", buyerCountry: "KEN" });
    return [...okRes(f), ...okRes(l), ...need(((f.j?.items || []) as unknown[]).length >= 1, "no financing option"), ...need(((l.j?.items || []) as unknown[]).length >= 1, "no logistics option")]; } },
  { id: 21, stage: "pricing", name: "origin prices: coffee from Ethiopia has several independent sources", run: async (c) => { const it = ((await c("/api/panel/commodities?product=coffee%20ethiopia&limit=60")).j?.items || []) as Record<string, unknown>[];
    const src = new Set(it.map((i) => String(i.source))); return [...need(it.length >= 5, `only ${it.length} rows`), ...need(src.size >= 3, `only ${src.size} sources: ${[...src].join(" / ").slice(0, 160)}`), ...need(it.slice(0, 12).some((i) => String(i.source_tier) === "T1"), "no official (T1) row among the first 12")]; } },
  { id: 22, stage: "pricing", name: "origin prices: sesame, rice and cocoa each have an official origin row from the last 150 days", run: async (c) => { const out: string[] = [];
    for (const p of ["sesame", "rice", "cocoa"]) { const it = ((await c(`/api/panel/commodities?product=${p}&limit=120`)).j?.items || []) as Record<string, unknown>[];
      if (!it.some((i) => String(i.source_tier) === "T1" && !!i.origin && (Date.now() - Date.parse(String(i.timestamp))) / 864e5 <= 150)) out.push(`${p}: no fresh official row with an origin`); }
    return out; } },
  { id: 20, stage: "pipeline", name: "deal pipeline, daily page, profile match and source coverage answer", run: async (c) => { const rs = await Promise.all(["/api/deal?pipeline=1", "/api/panel/today", "/api/match?mode=", "/api/panel/coverage"].map((p) => c(p)));
    return rs.flatMap((r, i) => okRes(r, 45000).map((e) => `${["pipeline", "today", "match", "coverage"][i]}: ${e}`)); } },
];
export async function scenarios(base: string, tok: string, from: number, n: number) {
  const call = async (path: string, body?: unknown): Promise<Res> => {
    const t0 = Date.now();
    try {
      const r = await fetch(base + path, { method: body ? "POST" : "GET", headers: { "content-type": "application/json", "x-dd-audit": tok }, body: body ? JSON.stringify(body) : undefined, signal: AbortSignal.timeout(70000) });
      const t = await r.text(); let j: Record<string, unknown> | null = null; try { j = JSON.parse(t); } catch { /* not json */ }
      return { status: r.status, ms: Date.now() - t0, j };
    } catch (e) { return { status: 0, ms: Date.now() - t0, j: { ok: false, error: String(e).slice(0, 120) } }; }
  };
  const out = [];
  for (const s of SCN.filter((x) => x.id > from).slice(0, n)) {
    const t0 = Date.now(); let fails: string[];
    try { fails = await s.run(call); } catch (e) { fails = ["crashed: " + String(e).slice(0, 160)]; }
    out.push({ id: s.id, stage: s.stage, name: s.name, pass: !fails.length, ms: Date.now() - t0, fails });
  }
  return out;
}
