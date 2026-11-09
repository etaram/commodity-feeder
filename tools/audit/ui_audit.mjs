// Phone-size walk through every panel view on the live site (read-only: views are opened, nothing is clicked that
// writes). Reports per view: page errors, console errors, failed API calls, horizontal overflow and its widest
// elements, visible "undefined/NaN/[object Object]", empty boxes and load time; saves a screenshot per view.
// Auth: the temporary audit token (header x-dd-audit), read by the workflow from the private state sheet.
import { chromium, devices } from "playwright";
import fs from "fs";

const TOKEN = process.env.AUDIT_TOKEN, BASE = process.env.BASE || "https://desk.sinder.pro";
const LANG = process.env.LANG_UI || "he";
const VIEWS = ((process.env.VIEWS || "").trim() || "today,forme,desk,tenders,deals,pipeline,projects,companies,contacts,markets,world,country,research,reverse,finance,logistics,grants,intel,jobs,clients,outreach,users,ops").split(",");
fs.mkdirSync("audit", { recursive: true });
const b = await chromium.launch();
const ctx = await b.newContext({ ...devices["iPhone 13"], deviceScaleFactor: 1, extraHTTPHeaders: { "x-dd-audit": TOKEN }, locale: LANG === "he" ? "he-IL" : "en-US" });
await ctx.addInitScript((lang) => { try { localStorage.setItem("sinder-panel-lang", lang); localStorage.setItem("lang", lang); } catch (e) {} }, LANG);
const page = await ctx.newPage();
let cur = "load";
const rep = {};
const R = (v) => (rep[v] ||= { pageerrors: [], console: [], failed: [], slow: [] });
page.on("pageerror", (e) => R(cur).pageerrors.push(String(e.message).slice(0, 300)));
page.on("console", (m) => { if (m.type() === "error") R(cur).console.push(m.text().slice(0, 300)); });
const started = new Map();
page.on("request", (q) => { if (q.url().includes("/api/")) started.set(q, Date.now()); });
page.on("requestfinished", async (q) => {
  if (!q.url().includes("/api/")) return;
  const r = await q.response(); const ms = Date.now() - (started.get(q) || Date.now());
  const path = q.url().replace(BASE, "").slice(0, 120) + (q.postData() ? " " + q.postData().slice(0, 60) : "");
  if (r && r.status() >= 400) R(cur).failed.push(`${r.status()} ${path}`);
  else if (r) { try { const j = await r.json(); if (j && j.ok === false) R(cur).failed.push(`ok:false ${path} ${String(j.error || j.code || "").slice(0, 120)}`); } catch {} }
  if (ms > 8000) R(cur).slow.push(`${ms}ms ${path}`);
});
page.on("requestfailed", (q) => { if (q.url().includes("/api/")) R(cur).failed.push(`neterr ${q.failure()?.errorText} ${q.url().replace(BASE, "").slice(0, 120)}`); });

const t0 = Date.now();
await page.goto(BASE + "/", { waitUntil: "domcontentloaded", timeout: 90000 });
await page.waitForTimeout(15000);
R("load").ms = Date.now() - t0;
R("load").url = page.url();
await page.screenshot({ path: `audit/00-load.png` });

const inspect = () => page.evaluate(() => {
  const W = window.innerWidth, out = { overflow: document.documentElement.scrollWidth - W, wide: [], bad: [], empty: [] };
  const vis = (el) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== "hidden"; };
  const view = [...document.querySelectorAll(".view")].find((v) => !v.hidden) || document.body;
  for (const el of view.querySelectorAll("*")) {
    if (!vis(el)) continue;
    const r = el.getBoundingClientRect();
    // something sticking out of the screen that is not inside a horizontal scroller
    if (r.right > W + 2 || r.left < -2) {
      let p = el.parentElement, scroller = false;
      while (p && p !== document.body) { const o = getComputedStyle(p).overflowX; if (o === "auto" || o === "scroll" || o === "hidden") { scroller = true; break; } p = p.parentElement; }
      if (!scroller) out.wide.push(`${el.tagName.toLowerCase()}${el.id ? "#" + el.id : ""}${el.className && typeof el.className === "string" ? "." + el.className.split(" ").slice(0, 2).join(".") : ""} w=${Math.round(r.width)} l=${Math.round(r.left)}`);
    }
    // a word broken into one-letter lines (a column squeezed to nothing)
    if (el.children.length === 0 && el.textContent.trim().length >= 4 && r.width < 22 && r.height > 60) out.wide.push(`squeezed "${el.textContent.trim().slice(0, 20)}" w=${Math.round(r.width)}`);
  }
  const txt = view.innerText || "";
  for (const m of txt.matchAll(/(undefined|NaN|\[object Object\]|null null|Invalid Date|\$-\d)/g)) out.bad.push(txt.slice(Math.max(0, m.index - 40), m.index + 30).replace(/\s+/g, " "));
  for (const e of view.querySelectorAll(".empty, .flash.err, .err")) if (vis(e) && e.textContent.trim()) out.empty.push(e.textContent.trim().slice(0, 120));
  out.textlen = txt.length;
  out.title = (view.querySelector("h1,h2")?.textContent || "").trim().slice(0, 60);
  return { ...out, wide: [...new Set(out.wide)].slice(0, 12), bad: [...new Set(out.bad)].slice(0, 8), empty: [...new Set(out.empty)].slice(0, 8) };
});

let i = 1;
for (const v of VIEWS) {
  cur = v;
  const t = Date.now();
  try { await page.evaluate((x) => { location.hash = x; }, v); } catch (e) { R(v).pageerrors.push("open: " + String(e).slice(0, 200)); }
  await page.waitForTimeout(9000);
  R(v).ms_after_open = Date.now() - t;
  try { Object.assign(R(v), await inspect()); } catch (e) { R(v).inspect_error = String(e).slice(0, 200); }
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: `audit/${String(i).padStart(2, "0")}-${v}.png`, fullPage: true }).catch(() => {});
  i++;
}
fs.writeFileSync("audit/report.json", JSON.stringify(rep, null, 1));
// search flows on the tenders view: a Hebrew word and an English word
for (const q of ["דאטה סנטר", "solar"]) {
  cur = "search:" + q;
  try {
    await page.evaluate(() => { location.hash = "tenders"; });
    await page.waitForTimeout(3000);
    await page.fill("#tq", q, { timeout: 8000 }); await page.press("#tq", "Enter"); await page.waitForTimeout(12000);
    Object.assign(R(cur), await inspect()); await page.screenshot({ path: `audit/${String(i++).padStart(2, "0")}-search-${q.replace(/\W+/g, "_") || "he"}.png` });
  } catch (e) { R(cur).note = "search: " + String(e).slice(0, 160); }
}
fs.writeFileSync("audit/report.json", JSON.stringify(rep, null, 1));
await b.close();
console.log(JSON.stringify(Object.fromEntries(Object.entries(rep).map(([k, v]) => [k, { err: v.pageerrors.length, cons: v.console.length, failed: v.failed.length, wide: (v.wide || []).length, bad: (v.bad || []).length }]))));
