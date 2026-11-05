import { createHash } from "crypto";
import { lookup } from "dns/promises";
import { decodeEntities, type Segment } from "@/lib/docextract";

// Bounded crawl of a client's official website (spec phase 6): at most 8 pages, same site only, robots.txt
// respected, no login / account / cart pages, HTML only. Page text is untrusted data: it is stored and quoted, never
// followed as instructions. Pages are deduplicated and cached by content hash. Server-side fetch only, with a
// private-network guard (no localhost, private or link-local addresses).

export type Fetcher = (url: string, init?: RequestInit) => Promise<Response>;
export type CrawlPage = { url: string; title: string; text: string; hash: string };
export type CrawlResult = { root: string; domain: string; pages: CrawlPage[]; skipped: { url: string; reason: string }[]; error?: string };

const UA = "SinderDealDesk/1.0 (+client onboarding; respects robots.txt)";
const MAX_PAGES = 8, MAX_BYTES = 1_500_000, TIMEOUT = 10_000, MAX_TEXT = 20_000;
const BLOCK_PATH = /\/(log-?in|sign-?in|sign-?up|register|account|my-?account|cart|basket|checkout|wp-admin|wp-login|admin|user|auth|password|cdn-cgi|feed|search|tag|author|privacy|cookie|terms|legal|careers?\/apply)(\/|$|\?|\.)/i;
const SKIP_EXT = /\.(pdf|jpe?g|png|gif|svg|webp|ico|zip|rar|7z|docx?|xlsx?|pptx?|mp4|mp3|avi|mov|css|js|json|xml|woff2?|ttf|eot)(\?|$)/i;
// pages most likely to state what the client sells, to whom, with what proof
const RELEVANT: [RegExp, number][] = [
  [/about|company|who-we-are|profile|overview|history/i, 5], [/product|solution|system|equipment|technolog|portfolio|catalog/i, 6],
  [/service|support|maintenance|installation/i, 4], [/industr|application|sector|market|use-case/i, 5],
  [/certif|quality|iso|standard|complian|approval/i, 5], [/reference|case|project|success|client|customer|partner|install/i, 5],
  [/export|global|international|distribut|dealer|office|location|worldwide/i, 3], [/contact/i, 2], [/news|blog|press|event/i, -2],
];

const cache = new Map<string, { at: number; page: CrawlPage | null; links: string[] }>();
const CACHE_MS = 24 * 3600e3;

export const contentHash = (t: string) => createHash("sha256").update(t.replace(/\s+/g, " ").trim().toLowerCase()).digest("hex").slice(0, 32);
export const siteOf = (host: string) => host.toLowerCase().replace(/^www\./, "");
export const sameSite = (host: string, site: string) => { const h = siteOf(host); return h === site || h.endsWith("." + site); };

// Private-network guard: literal addresses and resolved addresses must be public.
export function privateAddress(ip: string): boolean {
  const v = ip.toLowerCase();
  if (v === "::1" || v === "::" || v.startsWith("fe80:") || v.startsWith("fc") || v.startsWith("fd") || v.startsWith("::ffff:127.") || v.startsWith("::ffff:10.") || v.startsWith("::ffff:192.168.")) return true;
  const m = /^(\d+)\.(\d+)\.(\d+)\.(\d+)$/.exec(v.replace(/^::ffff:/, ""));
  if (!m) return false;
  const [a, b] = [Number(m[1]), Number(m[2])];
  return a === 10 || a === 127 || a === 0 || (a === 169 && b === 254) || (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) || (a === 100 && b >= 64 && b <= 127) || a >= 224;
}
export type Resolver = (host: string) => Promise<string[]>;
const dnsResolve: Resolver = async (host) => (await lookup(host, { all: true })).map((x) => x.address);
async function safeHost(host: string, resolve: Resolver): Promise<boolean> {
  const h = host.toLowerCase().replace(/^\[|\]$/g, "");
  if (!h || h === "localhost" || h.endsWith(".localhost") || h.endsWith(".local") || h.endsWith(".internal") || !h.includes(".") && !h.includes(":")) return false;
  if (/^[\d.]+$/.test(h) || h.includes(":")) return !privateAddress(h);
  try { const ips = await resolve(h); return ips.length > 0 && ips.every((ip) => !privateAddress(ip)); } catch { return false; }
}

// robots.txt: the group for our agent if present, else "*"; the longest matching Allow/Disallow wins.
export function robotsAllows(robots: string, path: string, agent = "sinderdealdesk"): boolean {
  const groups: { agents: string[]; rules: [boolean, string][] }[] = [];
  let cur: { agents: string[]; rules: [boolean, string][] } | null = null, lastWasAgent = false;
  for (const line of robots.split(/\r?\n/)) {
    const l = line.replace(/#.*/, "").trim(), m = /^([a-z-]+)\s*:\s*(.*)$/i.exec(l);
    if (!m) continue;
    const k = m[1].toLowerCase(), v = m[2].trim();
    if (k === "user-agent") { if (!cur || !lastWasAgent) { cur = { agents: [], rules: [] }; groups.push(cur); } cur.agents.push(v.toLowerCase()); lastWasAgent = true; continue; }
    lastWasAgent = false;
    if (cur && (k === "allow" || k === "disallow")) cur.rules.push([k === "allow", v]);
  }
  const g = groups.find((x) => x.agents.some((a) => a !== "*" && agent.includes(a))) || groups.find((x) => x.agents.includes("*"));
  if (!g) return true;
  let best: [boolean, number] = [true, -1];
  for (const [allow, pat] of g.rules) {
    if (!pat) continue;  // "Disallow:" (empty) allows everything
    const re = new RegExp("^" + pat.replace(/[.+?^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\\\$$/, "$"));
    if (re.test(path) && (pat.length > best[1] || (pat.length === best[1] && allow))) best = [allow, pat.length];
  }
  return best[0];
}

export function htmlToText(html: string): { title: string; text: string; links: string[] } {
  const title = decodeEntities((/<title[^>]*>([\s\S]*?)<\/title>/i.exec(html)?.[1] || "").replace(/\s+/g, " ").trim()).slice(0, 200);
  const links = [...html.matchAll(/<a\b[^>]*\bhref\s*=\s*["']([^"'#]+)["']/gi)].map((m) => decodeEntities(m[1].trim()));
  const body = html
    .replace(/<!--[\s\S]*?-->/g, " ")
    .replace(/<(script|style|noscript|svg|template|iframe|form|select)\b[\s\S]*?<\/\1>/gi, " ")
    .replace(/<(br|\/p|\/div|\/li|\/h[1-6]|\/tr|\/section|\/article|\/header|\/footer|\/table|\/ul|\/ol)\b[^>]*>/gi, "\n")
    .replace(/<(td|th)\b[^>]*>/gi, " | ")
    .replace(/<[^>]+>/g, " ");
  const text = decodeEntities(body).replace(/[ \t ]+/g, " ").replace(/ *\n */g, "\n").replace(/\n{2,}/g, "\n").trim().slice(0, MAX_TEXT);
  return { title, text, links };
}

async function get(url: string, f: Fetcher, site: string, resolve: Resolver, accept: RegExp): Promise<{ url: string; body: string } | { error: string }> {
  let cur = url;
  for (let hop = 0; hop < 4; hop++) {
    const u = new URL(cur);
    if (!/^https?:$/.test(u.protocol)) return { error: "not http(s)" };
    if (!sameSite(u.hostname, site)) return { error: `redirects off the site (${u.hostname})` };
    if (!(await safeHost(u.hostname, resolve))) return { error: "private or unresolvable address" };
    const ctl = new AbortController(), t = setTimeout(() => ctl.abort(), TIMEOUT);
    try {
      const r = await f(cur, { redirect: "manual", signal: ctl.signal, headers: { "user-agent": UA, accept: "text/html,text/plain;q=0.8" } });
      if (r.status >= 300 && r.status < 400) { const loc = r.headers.get("location"); if (!loc) return { error: `HTTP ${r.status}` }; cur = new URL(loc, cur).toString(); continue; }
      if (!r.ok) return { error: `HTTP ${r.status}` };
      const ct = r.headers.get("content-type") || "";
      if (ct && !accept.test(ct)) return { error: `not a web page (${ct.slice(0, 40)})` };
      const len = Number(r.headers.get("content-length") || 0);
      if (len > MAX_BYTES) return { error: "page too large" };
      const buf = Buffer.from(await r.arrayBuffer());
      return { url: cur, body: buf.subarray(0, MAX_BYTES).toString("utf-8") };
    } catch (e) { return { error: String((e as Error).name === "AbortError" ? "timed out" : (e as Error).message || e).slice(0, 80) }; }
    finally { clearTimeout(t); }
  }
  return { error: "too many redirects" };
}

export function normUrl(href: string, base: string): string | null {
  try {
    const u = new URL(href, base);
    if (!/^https?:$/.test(u.protocol)) return null;
    u.hash = "";
    for (const k of [...u.searchParams.keys()]) if (/^(utm_|fbclid|gclid|ref$|lang$|session|sid$)/i.test(k)) u.searchParams.delete(k);
    return u.toString().replace(/\/$/, "");
  } catch { return null; }
}

export function scoreUrl(u: string): number {
  const p = new URL(u);
  let path = p.pathname.toLowerCase();
  try { path = decodeURIComponent(path); } catch { /* keep the raw path */ }
  let s = 0;
  for (const [re, w] of RELEVANT) if (re.test(path)) s += w;
  s -= path.split("/").filter(Boolean).length;  // shallow pages first
  if (p.search) s -= 3;
  return s;
}

export function rankLinks(links: string[], base: string, site: string): string[] {
  const seen = new Set<string>(), out: { u: string; s: number }[] = [];
  for (const l of links) {
    const u = normUrl(l, base);
    if (!u || seen.has(u)) continue;
    seen.add(u);
    const p = new URL(u);
    if (!sameSite(p.hostname, site) || SKIP_EXT.test(p.pathname) || BLOCK_PATH.test(p.pathname + "/") || /^mailto:|^tel:|^javascript:/i.test(l)) continue;
    out.push({ u, s: scoreUrl(u) });
  }
  return out.sort((a, b) => b.s - a.s).map((x) => x.u);
}

export async function crawlSite(start: string, o: { fetch?: Fetcher; resolve?: Resolver; maxPages?: number } = {}): Promise<CrawlResult> {
  const f = o.fetch || ((u, i) => fetch(u, i)), resolve = o.resolve || dnsResolve, max = Math.min(o.maxPages || MAX_PAGES, MAX_PAGES);
  let root: URL;
  try { root = new URL(/^https?:\/\//i.test(start) ? start : `https://${start}`); } catch { return { root: start, domain: "", pages: [], skipped: [], error: "not a valid URL" }; }
  const site = siteOf(root.hostname), out: CrawlResult = { root: root.toString(), domain: site, pages: [], skipped: [] };
  if (!(await safeHost(root.hostname, resolve))) return { ...out, error: "the address is private or does not resolve" };
  const rb = await get(`${root.origin}/robots.txt`, f, site, resolve, /text\/plain|text\/html|^$/i);
  const robots = "body" in rb ? rb.body.slice(0, 200_000) : "";
  const queue = [normUrl(root.toString(), root.toString())!], seen = new Set<string>(queue), hashes = new Set<string>();
  while (queue.length && out.pages.length < max) {
    const url = queue.shift()!;
    const p = new URL(url);
    if (robots && !robotsAllows(robots, p.pathname + p.search)) { out.skipped.push({ url, reason: "disallowed by robots.txt" }); continue; }
    const hit = cache.get(url);
    let page: CrawlPage | null = null, links: string[] = [];
    if (hit && Date.now() - hit.at < CACHE_MS) ({ page, links } = hit);
    else {
      const r = await get(url, f, site, resolve, /text\/html|application\/xhtml|text\/plain/i);
      if ("error" in r) { out.skipped.push({ url, reason: r.error }); continue; }
      const h = htmlToText(r.body);
      if (/<input[^>]+type=["']?password/i.test(r.body) && h.text.length < 3000) { out.skipped.push({ url, reason: "login page" }); continue; }
      links = h.links.map((l) => normUrl(l, r.url)).filter((x): x is string => !!x);
      page = h.text.length >= 80 ? { url: r.url, title: h.title, text: h.text, hash: contentHash(h.text) } : null;
      if (cache.size > 2000) cache.clear();
      cache.set(url, { at: Date.now(), page, links });
    }
    if (!page) { out.skipped.push({ url, reason: "no readable text (script-rendered page?)" }); }
    else if (hashes.has(page.hash)) out.skipped.push({ url, reason: "duplicate content" });
    else { hashes.add(page.hash); out.pages.push(page); }
    // links are taken from the first pages only (home and top sections), ranked by relevance
    if (seen.size < 60) for (const l of rankLinks(links, url, site)) if (!seen.has(l)) { seen.add(l); queue.push(l); }
    queue.sort((a, b) => scoreUrl(b) - scoreUrl(a));
  }
  return out;
}

export const pagesToSegments = (r: CrawlResult): Segment[] => r.pages.map((p) => ({ ref: p.url, text: (p.title ? p.title + "\n" : "") + p.text }));
