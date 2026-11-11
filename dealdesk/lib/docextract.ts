import { inflateRawSync, inflateSync, constants as Z } from "zlib";

// Native text extraction for client onboarding (spec phase 6): PPTX (a zip of XML slides) and PDF (the text layer).
// No new dependency: a minimal zip reader on zlib and a minimal PDF object parser. No OCR: a page or slide without a
// text layer is reported as a gap (scanned page, image-only slide), never guessed. Input is untrusted data: sizes are
// capped, nothing in the file is executed or followed outside the file itself.

export type Segment = { ref: string; text: string };
export type Extracted = { kind: "pdf" | "pptx" | "text" | "html"; segments: Segment[]; gaps: { ref: string; reason: string }[]; error?: string };

const MAX_ENTRY = 8 * 1024 * 1024, MAX_TOTAL = 40 * 1024 * 1024, MAX_PAGES = 300;
// Upload limits, enforced on the server for every uploaded file (see sniffUpload and unzip).
export const UPLOAD_LIMITS = { bytes: 4_500_000, zipEntries: 2000, zipEntryBytes: MAX_ENTRY, zipTotalBytes: MAX_TOTAL } as const;

// ---------------------------------------------------------------- zip (PPTX, DOCX)
export function unzip(buf: Buffer, want: (name: string) => boolean): Map<string, Buffer> {
  const out = new Map<string, Buffer>();
  // End of central directory: signature 0x06054b50 within the last 64 KB + 22 bytes
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) throw new Error("not a zip file");
  const count = buf.readUInt16LE(eocd + 10), cdOff = buf.readUInt32LE(eocd + 16);
  let p = cdOff, total = 0;
  for (let n = 0; n < count && p + 46 <= buf.length; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) break;
    const method = buf.readUInt16LE(p + 10), csize = buf.readUInt32LE(p + 20), usize = buf.readUInt32LE(p + 24);
    const nlen = buf.readUInt16LE(p + 28), xlen = buf.readUInt16LE(p + 30), clen = buf.readUInt16LE(p + 32), loc = buf.readUInt32LE(p + 42);
    const name = buf.subarray(p + 46, p + 46 + nlen).toString("utf-8");
    p += 46 + nlen + xlen + clen;
    if (!want(name) || name.includes("..")) continue;
    if (usize > MAX_ENTRY || total + usize > MAX_TOTAL) continue;  // zip bomb guard (declared size)
    if (loc + 30 > buf.length || buf.readUInt32LE(loc) !== 0x04034b50) continue;
    const start = loc + 30 + buf.readUInt16LE(loc + 26) + buf.readUInt16LE(loc + 28);
    const data = buf.subarray(start, start + csize);
    try {
      // an entry may never inflate beyond the size its directory record declares (a lying record is skipped, not trusted)
      const body = method === 0 ? Buffer.from(data.subarray(0, MAX_ENTRY)) : method === 8 ? inflateRawSync(data, { maxOutputLength: Math.min(MAX_ENTRY, Math.max(1, usize)) }) : null;
      if (body && total + body.length > MAX_TOTAL) break;  // zip bomb guard (actual size)
      if (body) { out.set(name, body); total += body.length; }
    } catch { /* a broken entry is skipped; the slide is then reported as a gap */ }
  }
  return out;
}

// The central directory as declared: names, entry count and declared sizes. Nothing is decompressed here.
export function zipInventory(buf: Buffer, maxEntries = 100_000): { names: string[]; count: number; declared: number; largest: number } {
  let eocd = -1;
  for (let i = buf.length - 22; i >= Math.max(0, buf.length - 65557); i--) if (buf.readUInt32LE(i) === 0x06054b50) { eocd = i; break; }
  if (eocd < 0) throw new Error("not a zip file");
  const count = buf.readUInt16LE(eocd + 10), names: string[] = [];
  let p = buf.readUInt32LE(eocd + 16), declared = 0, largest = 0;
  for (let n = 0; n < count && n < maxEntries && p + 46 <= buf.length; n++) {
    if (buf.readUInt32LE(p) !== 0x02014b50) break;
    const usize = buf.readUInt32LE(p + 24), nlen = buf.readUInt16LE(p + 28);
    names.push(buf.subarray(p + 46, p + 46 + nlen).toString("utf-8"));
    declared += usize; largest = Math.max(largest, usize);
    p += 46 + nlen + buf.readUInt16LE(p + 30) + buf.readUInt16LE(p + 32);
  }
  return { names, count, declared, largest };
}

// What an uploaded file IS, decided from its bytes and never from its name or the browser's content type. Only a PDF
// and a PowerPoint PPTX are accepted. A macro-enabled deck (PPTM, PPSM, or any package carrying vbaProject.bin) is
// refused outright: nothing in an upload is ever executed, and a macro deck is not read at all.
export type Sniffed = { ok: true; kind: "pdf" | "pptx" } | { ok: false; status: 400 | 413 | 415 | 422; error: string };
export function sniffUpload(buf: Buffer): Sniffed {
  if (!buf.length) return { ok: false, status: 400, error: "the file is empty" };
  if (buf.length > UPLOAD_LIMITS.bytes) return { ok: false, status: 413, error: "the file is larger than 4.5 MB" };
  if (buf.subarray(0, 5).toString("latin1") === "%PDF-") return { ok: true, kind: "pdf" };
  if (buf.length >= 4 && buf.readUInt32LE(0) === 0x04034b50) {
    let inv: ReturnType<typeof zipInventory>;
    try { inv = zipInventory(buf, UPLOAD_LIMITS.zipEntries + 1); } catch { return { ok: false, status: 415, error: "unreadable package (send a PDF or a PPTX)" }; }
    if (inv.count > UPLOAD_LIMITS.zipEntries) return { ok: false, status: 422, error: `the package holds ${inv.count} entries (limit ${UPLOAD_LIMITS.zipEntries})` };
    if (inv.largest > UPLOAD_LIMITS.zipEntryBytes || inv.declared > UPLOAD_LIMITS.zipTotalBytes) return { ok: false, status: 422, error: "the package expands beyond the decompressed size limit (40 MB in total, 8 MB per part)" };
    let types = "";
    try { types = unzip(buf, (n) => n === "[Content_Types].xml").get("[Content_Types].xml")?.toString("utf-8") || ""; } catch { /* treated as no content types */ }
    if (inv.names.some((n) => /vbaProject\.bin$/i.test(n)) || /macroEnabled/i.test(types)) return { ok: false, status: 415, error: "macro-enabled presentations (PPTM, PPSM) are not accepted: save the deck as PPTX or PDF" };
    if (inv.names.includes("ppt/presentation.xml")) return { ok: true, kind: "pptx" };
    if (inv.names.some((n) => n.startsWith("word/"))) return { ok: false, status: 415, error: "Word documents are not supported yet (send a PDF or a PPTX)" };
    if (inv.names.some((n) => n.startsWith("xl/"))) return { ok: false, status: 415, error: "Excel workbooks are not supported yet (send a PDF or a PPTX)" };
    return { ok: false, status: 415, error: "not a PowerPoint file (send a PDF or a PPTX)" };
  }
  return { ok: false, status: 415, error: "only PDF and PPTX files are accepted (the file's content is neither)" };
}

const XML_ENT: Record<string, string> = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };
export function decodeEntities(s: string): string {
  return s.replace(/&(#x[0-9a-f]+|#\d+|[a-z]+);/gi, (m, e: string) => {
    if (e[0] === "#") { const c = e[1] === "x" || e[1] === "X" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10); return c > 0 && c < 0x110000 ? String.fromCodePoint(c) : ""; }
    return XML_ENT[e.toLowerCase()] ?? m;
  });
}

// DrawingML text: runs <a:t> inside paragraphs <a:p>; one line per paragraph.
function drawingText(xml: string): string {
  const paras = xml.split(/<\/a:p>/);
  const lines = paras.map((p) => [...p.matchAll(/<a:t(?:\s[^>]*)?>([\s\S]*?)<\/a:t>/g)].map((m) => decodeEntities(m[1])).join("")).map((l) => l.replace(/\s+/g, " ").trim());
  return lines.filter(Boolean).join("\n");
}

export function extractPptx(buf: Buffer): Extracted {
  let files: Map<string, Buffer>;
  try { files = unzip(buf, (n) => /^ppt\/(slides|notesSlides)\/[^/]+\.xml$/.test(n) || /^ppt\/(slides\/)?_rels\/[^/]+\.rels$/.test(n) || n === "ppt/presentation.xml"); }
  catch (e) { return { kind: "pptx", segments: [], gaps: [], error: String((e as Error).message || e).slice(0, 120) }; }
  // slide order from presentation.xml (sldIdLst -> relationship id -> slides/slideN.xml); numeric order as fallback
  const pres = files.get("ppt/presentation.xml")?.toString("utf-8") || "", rels = files.get("ppt/_rels/presentation.xml.rels")?.toString("utf-8") || "";
  const target = new Map([...rels.matchAll(/<Relationship\b[^>]*>/g)].map((m) => [/Id="([^"]+)"/.exec(m[0])?.[1] || "", (/Target="([^"]+)"/.exec(m[0])?.[1] || "").replace(/^\/?ppt\//, "")]));
  let order = [...pres.matchAll(/<p:sldId\b[^>]*r:id="([^"]+)"/g)].map((m) => "ppt/" + (target.get(m[1]) || "")).filter((n) => files.has(n));
  if (!order.length) order = [...files.keys()].filter((n) => /^ppt\/slides\/slide\d+\.xml$/.test(n)).sort((a, b) => parseInt(a.replace(/\D/g, "")) - parseInt(b.replace(/\D/g, "")));
  const segments: Segment[] = [], gaps: Extracted["gaps"] = [];
  order.slice(0, MAX_PAGES).forEach((name, i) => {
    const ref = `slide ${i + 1}`, xml = files.get(name)!.toString("utf-8");
    const text = drawingText(xml);
    if (text.length >= 3) segments.push({ ref, text }); else gaps.push({ ref, reason: /<p:pic\b/.test(xml) ? "image-only slide (no text layer; OCR not run)" : "empty slide" });
    // speaker notes are kept as their own reference: they often hold internal remarks (reviewed as possibly private)
    const relXml = files.get(name.replace("slides/", "slides/_rels/") + ".rels")?.toString("utf-8") || "";
    const note = /Target="\.\.\/notesSlides\/([^"]+)"/.exec(relXml)?.[1];
    const notes = note ? drawingText(files.get(`ppt/notesSlides/${note}`)?.toString("utf-8") || "").replace(/^\d+$/m, "").trim() : "";
    if (notes.length >= 3) segments.push({ ref: `${ref} notes`, text: notes });
  });
  if (!order.length) return { kind: "pptx", segments, gaps, error: "no slides found (not a PowerPoint file?)" };
  return { kind: "pptx", segments, gaps };
}

// ---------------------------------------------------------------- PDF (text layer)
type PName = { n: string };
type PRef = { r: number };
type PVal = number | boolean | null | string | PName | PRef | PVal[] | PDict | { s: Buffer };
type PDict = { d: Record<string, PVal> };
const isName = (v: unknown): v is PName => !!v && typeof v === "object" && "n" in (v as object);
const isRef = (v: unknown): v is PRef => !!v && typeof v === "object" && "r" in (v as object);
const isDict = (v: unknown): v is PDict => !!v && typeof v === "object" && "d" in (v as object);
const isStr = (v: unknown): v is { s: Buffer } => !!v && typeof v === "object" && "s" in (v as object);

const WS = new Set([0, 9, 10, 12, 13, 32]), DELIM = new Set("()<>[]{}/%".split("").map((c) => c.charCodeAt(0)));
// A small tokenizer shared by object bodies and content streams. Returns values and bare keywords (operators).
class Lexer {
  i = 0;
  constructor(public b: Buffer, start = 0, public end = b.length) { this.i = start; }
  skip() {
    while (this.i < this.end) {
      const c = this.b[this.i];
      if (WS.has(c)) this.i++;
      else if (c === 37) { while (this.i < this.end && this.b[this.i] !== 10 && this.b[this.i] !== 13) this.i++; }
      else break;
    }
  }
  literal(): Buffer {
    const out: number[] = []; let depth = 1; this.i++;
    while (this.i < this.end) {
      const c = this.b[this.i++];
      if (c === 92) {
        const n = this.b[this.i++];
        const map: Record<number, number> = { 110: 10, 114: 13, 116: 9, 98: 8, 102: 12, 40: 40, 41: 41, 92: 92 };
        if (n in map) out.push(map[n]);
        else if (n >= 48 && n <= 55) { let v = n - 48; for (let k = 0; k < 2 && this.b[this.i] >= 48 && this.b[this.i] <= 55; k++) v = v * 8 + this.b[this.i++] - 48; out.push(v & 255); }
        else if (n === 13) { if (this.b[this.i] === 10) this.i++; }
        else if (n !== 10) out.push(n);
      } else if (c === 40) { depth++; out.push(c); }
      else if (c === 41) { if (--depth === 0) break; out.push(c); }
      else out.push(c);
    }
    return Buffer.from(out);
  }
  hex(): Buffer {
    this.i++; let h = "";
    while (this.i < this.end && this.b[this.i] !== 62) { const ch = String.fromCharCode(this.b[this.i++]); if (/[0-9a-f]/i.test(ch)) h += ch; }
    this.i++;
    if (h.length % 2) h += "0";
    return Buffer.from(h, "hex");
  }
  word(): string { const s = this.i; while (this.i < this.end && !WS.has(this.b[this.i]) && !DELIM.has(this.b[this.i])) this.i++; return this.b.subarray(s, this.i).toString("latin1"); }
  // next value, or {op} for a keyword; undefined at the end
  next(depth = 0): PVal | { op: string } | undefined {
    this.skip();
    if (this.i >= this.end || depth > 40) return undefined;
    const c = this.b[this.i];
    if (c === 40) return { s: this.literal() };
    if (c === 60 && this.b[this.i + 1] === 60) {
      this.i += 2; const d: Record<string, PVal> = {};
      for (;;) {
        this.skip();
        if (this.i >= this.end) break;
        if (this.b[this.i] === 62 && this.b[this.i + 1] === 62) { this.i += 2; break; }
        const k = this.next(depth + 1);
        if (!isName(k)) { if (k === undefined) break; continue; }
        const v = this.next(depth + 1);
        if (v !== undefined && !(v && typeof v === "object" && "op" in v)) d[k.n] = v as PVal;
      }
      return { d };
    }
    if (c === 60) return { s: this.hex() };
    if (c === 91) {
      this.i++; const a: PVal[] = [];
      for (;;) {
        this.skip();
        if (this.i >= this.end) break;
        if (this.b[this.i] === 93) { this.i++; break; }
        const v = this.next(depth + 1);
        if (v === undefined) break;
        if (v && typeof v === "object" && "op" in v) { if (v.op === "R" && a.length >= 2 && typeof a[a.length - 1] === "number") { a.pop(); const num = a.pop() as number; a.push({ r: num }); } continue; }
        a.push(v);
      }
      return a;
    }
    if (c === 47) { this.i++; return { n: this.word().replace(/#([0-9a-f]{2})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))) }; }
    if (c === 41 || c === 62 || c === 93 || c === 123 || c === 125) { this.i++; return { op: String.fromCharCode(c) }; }
    const w = this.word();
    if (!w) { this.i++; return { op: "" }; }
    if (/^[+-]?(\d+\.?\d*|\.\d+)$/.test(w)) {
      // "12 0 R" is a reference
      const save = this.i;
      this.skip(); const w2 = this.word(); this.skip();
      if (/^\d+$/.test(w) && /^\d+$/.test(w2) && this.b[this.i] === 82 && (this.i + 1 >= this.end || WS.has(this.b[this.i + 1]) || DELIM.has(this.b[this.i + 1]))) { this.i++; return { r: parseInt(w, 10) }; }
      this.i = save; return parseFloat(w);
    }
    if (w === "true" || w === "false") return w === "true";
    if (w === "null") return null;
    return { op: w };
  }
}

type PObj = { v: PVal; stream?: Buffer };
function indexPdf(b: Buffer): { objs: Map<number, PObj>; trailer: PDict | null } {
  const objs = new Map<number, PObj>(); let trailer: PDict | null = null;
  const s = b.toString("latin1");
  const re = /(\d+)\s+(\d+)\s+obj\b/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(s))) {
    const num = parseInt(m[1], 10), lx = new Lexer(b, m.index + m[0].length);
    const v = lx.next();
    if (v === undefined || (v && typeof v === "object" && "op" in v)) continue;
    const o: PObj = { v: v as PVal };
    lx.skip();
    if (s.startsWith("stream", lx.i)) {
      let st = lx.i + 6;
      if (b[st] === 13) st++;
      if (b[st] === 10) st++;
      const len = isDict(v) && typeof v.d.Length === "number" ? v.d.Length : -1;
      let end = len >= 0 && s.startsWith("endstream", st + len) ? st + len : -1;
      if (end < 0 && len >= 0) { const k = s.indexOf("endstream", st + len); if (k >= 0 && k - st - len < 4) end = st + len; }
      if (end < 0) { end = s.indexOf("endstream", st); if (end < 0) end = b.length; while (end > st && (b[end - 1] === 10 || b[end - 1] === 13)) end--; }
      o.stream = b.subarray(st, end);
      re.lastIndex = end;
    }
    objs.set(num, o);  // a later definition (incremental update) replaces an earlier one
    if (isDict(v) && isName(v.d.Type) && v.d.Type.n === "XRef") trailer = v;
  }
  const t = s.lastIndexOf("trailer");
  if (t >= 0) { const v = new Lexer(b, t + 7).next(); if (isDict(v) && (v.d.Root || !trailer)) trailer = v; }
  return { objs, trailer };
}

function ascii85(b: Buffer): Buffer {
  const s = b.toString("latin1").replace(/\s/g, "").replace(/^<~/, "").replace(/~>.*$/, ""), out: number[] = [];
  let tuple = 0, n = 0;
  for (const ch of s) {
    if (ch === "z" && n === 0) { out.push(0, 0, 0, 0); continue; }
    const c = ch.charCodeAt(0) - 33; if (c < 0 || c > 84) continue;
    tuple = tuple * 85 + c;
    if (++n === 5) { out.push((tuple >>> 24) & 255, (tuple >>> 16) & 255, (tuple >>> 8) & 255, tuple & 255); tuple = 0; n = 0; }
  }
  if (n > 1) { for (let k = n; k < 5; k++) tuple = tuple * 85 + 84; for (let k = 0; k < n - 1; k++) out.push((tuple >>> (24 - 8 * k)) & 255); }
  return Buffer.from(out);
}

function decodeStream(dict: PDict, raw: Buffer): Buffer | null {
  const f = dict.d.Filter, filters = (Array.isArray(f) ? f : f ? [f] : []).map((x) => (isName(x) ? x.n : ""));
  let data = raw;
  for (const name of filters) {
    if (name === "FlateDecode" || name === "Fl") {
      try { data = inflateSync(data, { finishFlush: Z.Z_SYNC_FLUSH, maxOutputLength: MAX_ENTRY }); } catch { return null; }
    } else if (name === "ASCII85Decode" || name === "A85") data = ascii85(data);
    else if (name === "ASCIIHexDecode" || name === "AHx") data = Buffer.from(data.toString("latin1").replace(/[^0-9a-f]/gi, "").replace(/^(.(..)*)$/, "$10"), "hex");
    else return null;  // images (DCT, JBIG2, CCITT) and rare text filters: no text from this stream
  }
  return data;
}

class Pdf {
  objs: Map<number, PObj>; trailer: PDict | null;
  constructor(b: Buffer) {
    const ix = indexPdf(b); this.objs = ix.objs; this.trailer = ix.trailer;
    // objects packed in object streams (PDF 1.5+): /Type /ObjStm with N pairs of (number, offset) after /First
    for (const o of [...this.objs.values()]) {
      if (!isDict(o.v) || !isName(o.v.d.Type) || o.v.d.Type.n !== "ObjStm" || !o.stream) continue;
      const data = decodeStream(o.v, o.stream); if (!data) continue;
      const n = Number(o.v.d.N) || 0, first = Number(o.v.d.First) || 0, lx = new Lexer(data), pairs: number[] = [];
      for (let k = 0; k < n * 2; k++) { const v = lx.next(); if (typeof v !== "number") break; pairs.push(v); }
      for (let k = 0; k + 1 < pairs.length; k += 2) {
        if (this.objs.has(pairs[k])) continue;
        const v = new Lexer(data, first + pairs[k + 1]).next();
        if (v !== undefined && !(v && typeof v === "object" && "op" in v)) this.objs.set(pairs[k], { v: v as PVal });
      }
    }
  }
  get(v: PVal | undefined, depth = 0): PVal | undefined { return isRef(v) && depth < 20 ? this.get(this.objs.get(v.r)?.v, depth + 1) : v; }
  dict(v: PVal | undefined): PDict | null { const x = this.get(v); return isDict(x) ? x : null; }
  streamOf(v: PVal | undefined): Buffer | null {
    if (!isRef(v)) return null;
    const o = this.objs.get(v.r);
    return o && o.stream && isDict(o.v) ? decodeStream(o.v, o.stream) : null;
  }
  pages(): { page: PDict; res: PDict | null }[] {
    const out: { page: PDict; res: PDict | null }[] = [];
    const seen = new Set<PDict>();
    const walk = (node: PDict | null, res: PDict | null, depth: number) => {
      if (!node || depth > 30 || seen.has(node) || out.length >= MAX_PAGES) return;
      seen.add(node);
      const r = this.dict(node.d.Resources) || res;
      const kids = this.get(node.d.Kids);
      if (Array.isArray(kids)) for (const k of kids) walk(this.dict(k), r, depth + 1);
      else out.push({ page: node, res: r });
    };
    const root = this.dict(this.trailer?.d.Root);
    walk(this.dict(root?.d.Pages), null, 0);
    if (!out.length) {  // no usable trailer: every page object in file order
      for (const o of this.objs.values()) if (isDict(o.v) && isName(o.v.d.Type) && o.v.d.Type.n === "Page") out.push({ page: o.v, res: this.dict(o.v.d.Resources) });
    }
    return out;
  }
}

type Font = { two: boolean; map: Map<number, string> | null; codeLen: number };
function parseCMap(data: Buffer): { map: Map<number, string>; codeLen: number } {
  const s = data.toString("latin1"), map = new Map<number, string>();
  const cs = /begincodespacerange\s*<([0-9a-f]+)>/i.exec(s);
  const codeLen = cs ? Math.max(1, Math.ceil(cs[1].length / 2)) : 2;
  const u16 = (h: string) => { const b = Buffer.from(h.length % 4 ? h.padStart(Math.ceil(h.length / 4) * 4, "0") : h, "hex"); let o = ""; for (let i = 0; i + 1 < b.length; i += 2) o += String.fromCharCode(b.readUInt16BE(i)); return o; };
  for (const blk of s.matchAll(/beginbfchar([\s\S]*?)endbfchar/g)) for (const m of blk[1].matchAll(/<([0-9a-f]+)>\s*<([0-9a-f]*)>/gi)) map.set(parseInt(m[1], 16), u16(m[2]));
  for (const blk of s.matchAll(/beginbfrange([\s\S]*?)endbfrange/g)) {
    for (const m of blk[1].matchAll(/<([0-9a-f]+)>\s*<([0-9a-f]+)>\s*(<[0-9a-f]*>|\[[^\]]*\])/gi)) {
      const lo = parseInt(m[1], 16), hi = Math.min(parseInt(m[2], 16), lo + 65535);
      if (m[3][0] === "[") { [...m[3].matchAll(/<([0-9a-f]*)>/gi)].forEach((d, k) => { if (lo + k <= hi) map.set(lo + k, u16(d[1])); }); }
      else { const base = m[3].slice(1, -1); const head = base.slice(0, -4), last = parseInt(base.slice(-4) || "0", 16); for (let c = lo; c <= hi; c++) map.set(c, u16(head + (last + c - lo).toString(16).padStart(4, "0"))); }
    }
  }
  return { map, codeLen };
}

function pageText(pdf: Pdf, content: Buffer, res: PDict | null, depth = 0): string {
  const fonts = new Map<string, Font>();
  const fontFor = (name: string): Font => {
    if (fonts.has(name)) return fonts.get(name)!;
    const fd = pdf.dict(pdf.dict(res?.d.Font)?.d[name]);
    const two = isName(fd?.d.Subtype) && fd!.d.Subtype.n === "Type0";
    const cm = fd?.d.ToUnicode ? pdf.streamOf(fd.d.ToUnicode as PVal) : null;
    const parsed = cm ? parseCMap(cm) : null;
    const f: Font = { two, map: parsed?.map || null, codeLen: parsed ? (two ? Math.max(2, parsed.codeLen) : parsed.codeLen) : two ? 2 : 1 };
    fonts.set(name, f);
    return f;
  };
  const show = (b: Buffer, f: Font | null): string => {
    if (!f) return b.toString("latin1");
    let o = "";
    for (let i = 0; i + f.codeLen - 1 < b.length; i += f.codeLen) {
      const code = f.codeLen === 1 ? b[i] : f.codeLen === 2 ? b.readUInt16BE(i) : parseInt(b.subarray(i, i + f.codeLen).toString("hex"), 16);
      const u = f.map?.get(code);
      if (u !== undefined) o += u;
      else if (!f.two) o += String.fromCharCode(code);  // simple font without a map: Latin-1 / WinAnsi approximation
    }
    return o;
  };
  const lx = new Lexer(content), stack: (PVal | { op: string })[] = [];
  let out = "", font: Font | null = null;
  const nl = () => { if (out && !out.endsWith("\n")) out += "\n"; };
  for (let guard = 0; guard < 2_000_000; guard++) {
    const t = lx.next();
    if (t === undefined) break;
    if (!(t && typeof t === "object" && "op" in t)) { stack.push(t); if (stack.length > 64) stack.shift(); continue; }
    const op = t.op, a = stack.splice(0);
    if (op === "BI") { const k = content.indexOf("EI", lx.i); lx.i = k < 0 ? content.length : k + 2; continue; }  // inline image data
    if (op === "Tf" && isName(a[0])) font = fontFor(a[0].n);
    else if (op === "Tj" && isStr(a[0])) out += show(a[0].s, font);
    else if ((op === "'" || op === '"') && isStr(a[a.length - 1])) { nl(); out += show((a[a.length - 1] as { s: Buffer }).s, font); }
    else if (op === "TJ" && Array.isArray(a[0])) { for (const x of a[0]) { if (isStr(x)) out += show(x.s, font); else if (typeof x === "number" && x < -180 && !out.endsWith(" ")) out += " "; } }
    else if (op === "T*" || op === "ET") nl();
    else if ((op === "Td" || op === "TD") && typeof a[1] === "number" && Math.abs(a[1]) > 0.5) nl();
    else if ((op === "Td" || op === "TD") && typeof a[0] === "number" && a[0] > 1 && !out.endsWith(" ") && !out.endsWith("\n")) out += " ";
    else if (op === "Tm") nl();
    else if (op === "Do" && isName(a[0]) && depth < 3) {
      const ref = pdf.dict(res?.d.XObject)?.d[a[0].n], xo = isRef(ref) ? pdf.objs.get(ref.r) : undefined;
      if (xo && isDict(xo.v) && isName(xo.v.d.Subtype) && xo.v.d.Subtype.n === "Form") { const data = pdf.streamOf(ref); if (data) { nl(); out += pageText(pdf, data, pdf.dict(xo.v.d.Resources) || res, depth + 1); nl(); } }
    }
  }
  return out;
}

const tidy = (t: string) => t.replace(/\u0000/g, "").replace(/[ \t]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{3,}/g, "\n\n").trim();

export function extractPdf(buf: Buffer): Extracted {
  if (buf.subarray(0, 1024).toString("latin1").indexOf("%PDF-") < 0) return { kind: "pdf", segments: [], gaps: [], error: "not a PDF file" };
  let pdf: Pdf;
  try { pdf = new Pdf(buf); } catch (e) { return { kind: "pdf", segments: [], gaps: [], error: `unreadable PDF: ${String((e as Error).message || e).slice(0, 120)}` }; }
  if (pdf.trailer?.d.Encrypt) return { kind: "pdf", segments: [], gaps: [{ ref: "document", reason: "encrypted PDF (ask the client for an unprotected copy)" }], error: "encrypted PDF" };
  const segments: Segment[] = [], gaps: Extracted["gaps"] = [];
  const pages = pdf.pages();
  pages.forEach(({ page, res }, i) => {
    const ref = `page ${i + 1}`;
    // Contents: one stream reference, an array of them, or a reference to such an array
    const raw = page.d.Contents;
    let parts: PVal[] = Array.isArray(raw) ? raw : raw === undefined ? [] : [raw];
    if (parts.length === 1 && isRef(parts[0])) { const o = pdf.objs.get(parts[0].r); if (o && !o.stream && Array.isArray(o.v)) parts = o.v; }
    const bufs = parts.map((p) => pdf.streamOf(p)).filter((x): x is Buffer => !!x);
    let text = "";
    try { text = tidy(pageText(pdf, Buffer.concat(bufs.flatMap((b) => [b, Buffer.from("\n")])), res)); } catch { text = ""; }
    if (text.replace(/\s/g, "").length >= 12) segments.push({ ref, text });
    else gaps.push({ ref, reason: "no text layer (scanned or image-only page; OCR not run)" });
  });
  if (!pages.length) return { kind: "pdf", segments, gaps, error: "no pages found" };
  return { kind: "pdf", segments, gaps };
}

// ---------------------------------------------------------------- uploads: content decides, the file name does not
export function extractUpload(buf: Buffer): Extracted & { status?: number } {
  const k = sniffUpload(buf);
  if (!k.ok) return { kind: "pdf", segments: [], gaps: [], error: k.error, status: k.status };
  return k.kind === "pdf" ? extractPdf(buf) : extractPptx(buf);
}

// ---------------------------------------------------------------- dispatcher (trusted callers and tests; uploads use extractUpload)
export function extractDocument(buf: Buffer, filename = ""): Extracted {
  const head = buf.subarray(0, 8).toString("latin1"), ext = filename.toLowerCase().split(".").pop() || "";
  if (head.startsWith("%PDF") || ext === "pdf") return extractPdf(buf);
  if (head.startsWith("PK")) {
    if (ext === "pptx" || ext === "ppsx" || ext === "" || ext === "zip") return extractPptx(buf);
    return { kind: "pptx", segments: [], gaps: [], error: `unsupported file type .${ext} (send PDF or PPTX)` };
  }
  if (["txt", "md", "csv"].includes(ext) || /^[\x09\x0a\x0d\x20-\x7e -￿]*$/.test(buf.subarray(0, 2000).toString("utf-8"))) {
    const text = tidy(buf.toString("utf-8").slice(0, 200_000));
    // a plain text brief: one segment per ~3,000 characters, referenced by part
    const segs: Segment[] = [];
    for (let i = 0, k = 1; i < text.length; i += 3000, k++) segs.push({ ref: `part ${k}`, text: text.slice(i, i + 3000) });
    return { kind: "text", segments: segs, gaps: [] };
  }
  return { kind: "pdf", segments: [], gaps: [], error: "unsupported file type (send PDF or PPTX)" };
}
