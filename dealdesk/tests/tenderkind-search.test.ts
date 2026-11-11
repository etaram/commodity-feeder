// The flag TENDER_KIND in the real supplier search (lib/panel.ts supplierSearch), end to end and without a network:
// fetch is replaced, and the supplier index is a small encrypted file of fictional companies built here.
// Proves: with the flag off (the default) a tender request returns exactly what it returned before the flag existed,
// whether or not the request carries the tender's title; with the flag on, a tender that buys no goods returns no
// supplier and a note, and a goods tender is searched by its product phrase. Run: npm test
import { createCipheriv, randomBytes } from "crypto";
import { gzipSync } from "zlib";
import { NO_GOODS_NOTE, supplierSearch, type SupQuery } from "@/lib/panel";
let fail = 0;
const ok = (name: string, cond: boolean, got?: unknown) => { if (!cond) fail++; console.log(`${cond ? "ok  " : "FAIL"} ${name}${cond ? "" : " - got " + JSON.stringify(got)}`); };

const INDEX = [
  { n: "Voltaro Gensets Ltd", c: "TUR", rg: "Europe", tr: "1", q: 80, ty: "goods supplier", s: "Energy & power equipment", p: "diesel generators 20-2000 kVA, alternators", web: "voltaro.example" },
  { n: "Petromar Fuels SA", c: "ARE", rg: "Middle East", tr: "1", q: 70, ty: "goods supplier", s: "Fuels & lubricants", p: "diesel, gasoline, jet fuel trading", web: "petromar.example" },
  { n: "Northfield Dairy Co", c: "KEN", rg: "Africa", tr: "2", q: 60, ty: "goods supplier", s: "Agriculture & food", p: "milk, yoghurt, butter", web: "northfield.example" },
  { n: "Hospital Linen Works", c: "IND", rg: "Asia", tr: "2", q: 55, ty: "goods supplier", s: "Textiles", p: "hospital bed sheets, surgical gowns", web: "linen.example" },
  { n: "Aquaflow Pumps GmbH", c: "DEU", rg: "Europe", tr: "1", q: 75, ty: "goods supplier", s: "Water & sanitation", p: "water pumps, water supply system components, valves", web: "aquaflow.example" },
  { n: "Lotus Paper Mills", c: "IDN", rg: "Asia", tr: "2", q: 50, ty: "goods supplier", s: "Paper & packaging", p: "copy paper, tissue", web: "lotus.example" },
];
const key = randomBytes(32), nonce = randomBytes(12), c = createCipheriv("aes-256-gcm", key, nonce);
const body = Buffer.concat([c.update(gzipSync(Buffer.from(JSON.stringify(INDEX)))), c.final()]);
const file = Buffer.concat([nonce, body, c.getAuthTag()]);
process.env.WEB_INDEX_KEY = key.toString("base64");
for (const k of ["ANTHROPIC_API_KEY", "GOOGLE_SERVICE_ACCOUNT_JSON", "TENDER_KIND"]) delete process.env[k];
let calls = 0;
globalThis.fetch = (async (url: unknown) => { calls++; return /suppliers\.enc$/.test(String(url)) ? new Response(file) : new Response("", { status: 404 }); }) as typeof fetch;
for (const k of ["log", "info", "warn", "error"] as const) { const say = console[k]; console[k] = (...a: unknown[]) => { if (/^(ok  |FAIL)/.test(String(a[0]))) say(...a); }; }

const goodsTitle = "Supply and delivery of 500 kVA diesel generators to Northfield hospital, Lot 2";
const worksTitle = "Rehabilitation of water supply system for the Northfield hospital";
const plain = (title: string): SupQuery => ({ sector: "", text: `${title} `, country: "", region: "", hs: "", n: 15 });
const asTender = (title: string): SupQuery => ({ ...plain(title), tender: { title, category: "" } });
const names = (r: { values: string[][] }) => r.values.slice(1).map((x) => x[r.values[0].indexOf("supplier")]);

(async () => {
  // flag off: the request with the tender's title gives the same answer, byte for byte, as the request without it
  for (const flag of [undefined, "off", "ON", "1"]) {
    if (flag === undefined) delete process.env.TENDER_KIND; else process.env.TENDER_KIND = flag;
    for (const title of [goodsTitle, worksTitle]) {
      const a = await supplierSearch(plain(title)), b = await supplierSearch(asTender(title));
      ok(`flag ${JSON.stringify(flag)}: unchanged output for "${title.slice(0, 40)}..."`, JSON.stringify(a) === JSON.stringify(b) && !("note" in b) && !("tender_kind" in b), b);
    }
  }
  delete process.env.TENDER_KIND;
  const offGoods = await supplierSearch(asTender(goodsTitle)), offWorks = await supplierSearch(asTender(worksTitle));
  // today's behaviour, pinned: any one title word is enough, so the fuel trader, the dairy and the linen maker come back
  ok("flag off, goods tender: the any-word result of today", JSON.stringify([...names(offGoods)].sort()) === JSON.stringify(["Hospital Linen Works", "Northfield Dairy Co", "Petromar Fuels SA", "Voltaro Gensets Ltd"]) && offGoods.total === 4, names(offGoods));
  ok("flag off, works tender: suppliers are returned, as today", JSON.stringify([...names(offWorks)].sort()) === JSON.stringify(["Aquaflow Pumps GmbH", "Hospital Linen Works", "Northfield Dairy Co"]), names(offWorks));
  ok("flag off: the answer has the four fields it always had", JSON.stringify(Object.keys(offGoods)) === JSON.stringify(["values", "total", "origins", "query"]), Object.keys(offGoods));

  process.env.TENDER_KIND = "on";
  const before = calls, onWorks = await supplierSearch(asTender(worksTitle));
  ok("flag on, works tender: no supplier, the note, the same header row", onWorks.values.length === 1 && JSON.stringify(onWorks.values[0]) === JSON.stringify(offWorks.values[0]) && onWorks.total === 0 && onWorks.note === NO_GOODS_NOTE && onWorks.tender_kind === "non_goods", onWorks);
  ok("flag on, works tender: answered before anything is read", calls === before);
  const onGoods = await supplierSearch(asTender(goodsTitle));
  ok("flag on, goods tender: searched by the product phrase, so the place and the buyer no longer match", !names(onGoods).includes("Northfield Dairy Co") && !names(onGoods).includes("Hospital Linen Works") && names(onGoods).includes("Voltaro Gensets Ltd") && !onGoods.note && onGoods.tender_kind === "goods", names(onGoods));
  const onPlain = await supplierSearch(plain(worksTitle));
  ok("flag on, a request that is not a tender request: unchanged", JSON.stringify(onPlain) === JSON.stringify(await (async () => { delete process.env.TENDER_KIND; return supplierSearch(plain(worksTitle)); })()));
  process.exit(fail ? 1 : 0);
})().catch((e) => { console.log(`FAIL the search ran - got ${String(e).slice(0, 300)}`); process.exit(1); });
