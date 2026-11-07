(() => {
  "use strict";
  // Report browser errors to the hidden ops log (a few per page load).
  let sent = 0;
  const report = (message, where) => { if (sent >= 5) return; sent++; try { fetch("/api/panel/log", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify({ message: String(message).slice(0, 300), where: String(where || "").slice(0, 200), ua: navigator.userAgent.slice(0, 120) }) }).catch(() => {}); } catch (e) {} };
  window.addEventListener("error", e => report(e.message, (e.filename || "") + ":" + (e.lineno || "")));
  window.addEventListener("unhandledrejection", e => report("unhandled: " + (e.reason && e.reason.message || e.reason), location.pathname));
  const RANGE_KEY = {
    "'My Leads'!A1:AE1500": "tenders", "'Titles HE'!A1:B20000": "titles", "'BD Agent'!A1:M600": "bd",
    "'Key Accounts'!A1:S400": "accounts", "'Repeat Buyers'!A1:O5600": "repeat", "'Market Signals'!A1:O3200": "markets",
    "'Plays'!A1:N400": "plays", "'FX'!A1:D40": "fx", "'Attention'!A1:G400": "attention", "'Meta'!A1:B5": "meta", "'Intel'!A1:P2000": "intel", "'Upcoming'!A1:AE1500": "upcoming", "'Stats'!A1:B60": "stats",
    "'Pursuits'!A1:V600": "pursuits", "'Panel Jobs'!A1:L800": "jobs", "'Suppliers'!A1:AJ6001": "suppliers",
    "'Grants'!A1:L1500": "grants", "'Exempt Buys'!A1:Q4001": "exempt", "'IL Exemption Contracts'!A1:R3000": "ilex", "'Integrity'!A1:N300": "integrity", "'Contacts'!A1:S1500": "contacts", "'Projects'!A1:V300": "projects", "'Project Tasks'!A1:L3000": "ptasks", "'Approvals'!A1:M2000": "approvals",
  };
  const SU = "1crzrRr4qrgt1WpAwNmCNPL4TfIrZUuTyqRGonVvwhuA";
  const lastSearch = {};
  const err = (code, server, message) => Object.assign(new Error(message || code), { code, server, message });

  async function post(url, body, server) {
    server = server || "Deal Desk";
    let r;
    try { r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), credentials: "same-origin" }); }
    catch (e) { throw Object.assign(err("server_unavailable", "Deal Desk"), { retryable: true }); }
    if (r.status === 401) { location.href = "/login"; throw err("needs_reauth", "Deal Desk"); }
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.ok === false) throw err(j.code || "tool_error", server, j.error || String(r.status));
    return j;
  }

  const mcp = {
    async callTool(server, tool, args, opts) {
      if (server === "Google Sheets") {
        const range = String(args.range || "");
        if (tool === "get_values") {
          if (range.startsWith("'Panel Search'!A9")) {
            const kind = args.spreadsheetId === SU ? "c" : "t";
            const j = await post("/api/panel/search", { kind, values: lastSearch[kind] || [] });
            return { payload: { values: j.values, total: j.total }, cache: { storedAt: Date.now() } };
          }
          const key = range === "'Panel Search'!A6:B6" ? "tot_t" : range === "'Panel Search'!D1:E1" ? "tot_s" : RANGE_KEY[range];
          if (!key) throw err("tool_error", "Google Sheets", "range not available on the web: " + range);
          const j = await post("/api/panel/get", { key, fresh: !!(opts && opts.cache && opts.cache.refresh) });
          return { payload: { values: j.values }, cache: { storedAt: j.at || Date.now() } };
        }
        if (tool === "update_values" && range.startsWith("'Panel Search'!")) {
          lastSearch[args.spreadsheetId === SU ? "c" : "t"] = args.values || [];
          return { payload: {} };
        }
        if (tool === "append_values") {
          await post("/api/panel/append", { range, values: args.values }, "Google Sheets (writing from the web)");
          return { payload: {} };
        }
        throw err("tool_error", "Google Sheets", "not available on the web");
      }
      if (server === "Gmail") throw err("server_not_connected", "Gmail");
      throw err("server_not_connected", server);
    },
  };

  let aiOn = null;
  // Browser cache: the same question is not paid for twice within a day.
  async function ai(prompt, opts) {
    let k = "";
    try { const b = new TextEncoder().encode(prompt); const d = await crypto.subtle.digest("SHA-256", b); k = "ai2:" + Array.from(new Uint8Array(d)).map((x) => x.toString(16).padStart(2, "0")).join(""); const c = JSON.parse(localStorage.getItem(k) || "null"); if (c && Date.now() - c.at < 86400000) return c.text; } catch (e) {}
    let j;
    try { j = await post("/api/panel/ai", { prompt, tier: opts && opts.modelTier }); }
    catch (e) { e.text = "AI: " + (e.message || e.code || "error"); throw e; }
    const text = j.text || "";
    try { if (k && text) localStorage.setItem(k, JSON.stringify({ text, at: Date.now() })); } catch (e) {}
    return text;
  }
  const sample = async (prompt, opts) => {
    const text = await ai(prompt, opts);
    if (opts && typeof opts.onText === "function") opts.onText({ text });
    return { text };
  };
  sample.json = async (prompt, opts) => {
    const text = await ai(prompt + "\n\nReply with valid JSON only, no prose and no code fences.", opts);
    const m = text.match(/[\[{][\s\S]*[\]}]/);
    return JSON.parse(m ? m[0] : text);
  };

  // Instant jobs on the web: the server researches now (Claude Haiku 5.5 with web search) instead of queueing for the worker.
  window.DD_INSTANT = async (job) => post("/api/panel/run", job, "Deal Desk AI");
  window.DD_FIN = { list: () => getj("/api/panel/finance"), forDeal: (q) => post("/api/panel/finance", q, "Deal Desk") };
  window.DD_LOG = { list: () => getj("/api/panel/logistics"), forDeal: (q) => post("/api/panel/logistics", q, "Deal Desk") };
  window.DD_TODAY = async (focus) => { const r = await fetch("/api/panel/today" + (focus ? "?focus=" + encodeURIComponent(focus) : ""), { credentials: "same-origin" }); const j = await r.json().catch(() => ({})); if (!r.ok || j.ok === false) throw err(j.code || "tool_error", "Deal Desk", j.error || String(r.status)); return j; };
  // search all tenders (or suppliers) on the server: a word or an id, optionally in one country
  window.DD_SEARCH = async (o) => post("/api/panel/search", { kind: o.kind || "t", values: o.kind === "c" ? [[o.q || ""]] : [[String(o.q || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "country", o.country || ""]] });
  window.DD_TX = async (lang, items) => post("/api/panel/translate", { lang, items }, "Deal Desk AI");
  // The signed-in user ({email, name, role}); the panel shows a badge and hides what the role cannot do.
  window.DD_ME = fetch("/api/me", { credentials: "same-origin" }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  window.DD_LOGOUT = async () => { await fetch("/api/logout", { method: "POST", credentials: "same-origin" }).catch(() => {}); location.href = "/login"; };
  // Activity log: what the signed-in user opens (fire and forget), and the admin's view of everyone's actions.
  window.DD_TRACK = (action, target, detail) => { fetch("/api/activity", { method: "POST", headers: { "Content-Type": "application/json" }, credentials: "same-origin", keepalive: true, body: JSON.stringify({ action, target: String(target || "").slice(0, 300), detail: String(detail || "").slice(0, 300) }) }).catch(() => {}); };
  window.DD_SUMMARY = async (days) => { const r = await fetch("/api/activity?summary=1&days=" + (days || 30), { credentials: "same-origin" }); const j = await r.json().catch(() => ({})); if (!r.ok) throw err(j.code || "tool_error", "Deal Desk", j.error || String(r.status)); return j.users || []; };
  window.DD_ACTIVITY = async (email) => { const r = await fetch("/api/activity?limit=1000" + (email ? "&email=" + encodeURIComponent(email) : ""), { credentials: "same-origin" }); const j = await r.json().catch(() => ({})); if (!r.ok) throw err(j.code || "tool_error", "Deal Desk", j.error || String(r.status)); return j.rows || []; };
  // Personal profile and matches (scored on the server from the tender index, no AI).
  const getj = async (url) => { const r = await fetch(url, { credentials: "same-origin" }); if (r.status === 401) { location.href = "/login"; throw err("needs_reauth", "Deal Desk"); } const j = await r.json().catch(() => ({})); if (!r.ok || j.ok === false) throw err(j.code || "tool_error", "Deal Desk", j.error || String(r.status)); return j; };
  window.DD_PROFILE = {
    get: (facets) => getj("/api/profile" + (facets ? "?facets=1" : "")),
    preview: (profile) => post("/api/profile", { profile, preview: true }),
    save: (profile, inferSectors) => post("/api/profile", { profile, inferSectors: !!inferSectors }),
    feedback: (kind, id) => post("/api/profile", { [kind]: id }),
    views: (views) => post("/api/profile", { views }),
  };
  window.DD_MATCH = (mode) => getj("/api/match?" + (mode === "saved" ? "saved=1" : "mode=" + encodeURIComponent(mode || "") + "&limit=150"));
  // Admin only: user accounts (list, approve, change role, disable).
  window.DD_USERS = {
    list: async () => { const r = await fetch("/api/users", { credentials: "same-origin" }); if (r.status === 401) { location.href = "/login"; throw err("needs_reauth", "Deal Desk"); } const j = await r.json().catch(() => ({})); if (!r.ok) throw err(j.code || "tool_error", "Deal Desk", j.error || String(r.status)); return j.users || []; },
    set: async (email, patch) => post("/api/users", Object.assign({ email }, patch), "Deal Desk"),
  };
  // The best suppliers for one tender, ranked on the server over the whole supplier index.
  window.DD_SUPFOR = async (q) => (await post("/api/panel/suppliers-for", q, "Deal Desk")).values || [];
  // Private deal workspace (analysts and admins; the server refuses viewers).
  window.DD_DEAL = {
    get: async (id) => { const r = await fetch("/api/deal?id=" + encodeURIComponent(id), { credentials: "same-origin" }); const j = await r.json().catch(() => ({})); if (!r.ok || j.ok === false) throw err(j.code || "tool_error", "Deal Desk", j.error || String(r.status)); return j; },
    docs: (deal_id, url) => post("/api/deal/docs", { deal_id, url }, "Deal Desk AI"),
    save: (deal_id, kind, data, record_id, del) => post("/api/deal", { deal_id, kind, data, record_id, delete: !!del }, "Deal Desk"),
    pipeline: () => getj("/api/deal?pipeline=1"),
  };
  window.DD_TG = () => getj("/api/telegram/code");
  window.DD_REVERSE = (body) => post("/api/panel/reverse", body, "Deal Desk AI");
  window.DD_PUSH = { key: () => getj("/api/push"), save: (subscription, lang) => post("/api/push", { subscription, lang }, "Deal Desk") };
  if ("serviceWorker" in navigator && location.protocol === "https:") navigator.serviceWorker.register("/sw.js", { updateViaCache: "none" }).catch(() => {});
  window.DD_TG_SETUP = { get: () => getj("/api/telegram/setup"), set: () => post("/api/telegram/setup", {}, "Deal Desk") };
  window.DD_LABEL = (b) => post("/api/panel/label", b, "Deal Desk");
  window.DD_COSTS = (b) => post("/api/panel/costs", b, "Deal Desk AI");
  window.DD_SENDMAIL = (b) => post("/api/panel/sendmail", b, "Deal Desk");
  // World and project intelligence (events, project timelines, hypotheses), from the pipeline CSVs.
  window.DD_INTEL = (q) => getj("/api/panel/intel" + (q ? "?" + new URLSearchParams(q).toString() : ""));
  window.DD_ASSERT = {
    list: (entity, country, property) => getj("/api/panel/assertions?entity=" + encodeURIComponent(entity || "") + "&country=" + encodeURIComponent(country || "") + (property ? "&property=" + encodeURIComponent(property) : "")),
    add: (a) => post("/api/panel/assertions", a, "Deal Desk"),
    quarantine: (id, status, reason) => post("/api/panel/assertions", { quarantine: id, status, reason }, "Deal Desk"),
  };
  window.DD_COMMODITIES = (q) => getj("/api/panel/commodities?" + new URLSearchParams({ product: (q && q.product) || "", hs6: (q && q.hs6) || "", limit: String((q && q.limit) || 200) }));
  window.DD_CHECK = {
    get: (name, country) => getj("/api/panel/company-check?name=" + encodeURIComponent(name || "") + "&country=" + encodeURIComponent(country || "")),
    request: (name, country) => post("/api/panel/company-check", { name, country }, "Deal Desk"),
    summary: () => getj("/api/panel/company-check?summary=1"),
  };
  window.DD_ADMIN = () => getj("/api/panel/admin");
  window.DD_ADMIN_ACT = (action) => post("/api/panel/admin", { action }, "Deal Desk");
  window.DD_AI_USAGE = (days) => getj("/api/panel/ai-usage?days=" + (days || 7));
  window.DD_STRATEGY = { get: () => getj("/api/panel/strategy"), save: (b) => post("/api/panel/strategy", b, "Deal Desk") };
  // Client intake: dossiers from the client's own deck and site, target profiles and prospects. PUT returns the body
  // with its HTTP status (409 stale version, 422 blockers) so the screen can show why a change was refused.
  const ddput = async (u, b) => { const r = await fetch(u, { method: "PUT", headers: { "Content-Type": "application/json" }, credentials: "same-origin", body: JSON.stringify(b) }); if (r.status === 401) { location.href = "/login"; throw err("needs_reauth", "Deal Desk"); } const j = await r.json().catch(() => ({ ok: false })); return Object.assign({ status: r.status }, j); };
  const cid = (id) => "/api/clients/" + encodeURIComponent(id);
  window.DD_CLIENTS = {
    list: () => getj("/api/clients"),
    create: (b) => post("/api/clients", b, "Deal Desk"),
    get: (id) => getj(cid(id)),
    save: (id, patch) => ddput(cid(id), patch),
    ingest: (id, b) => post(cid(id) + "/ingest", b, "Deal Desk AI"),
    targets: (id, b) => post(cid(id) + "/targets", b || {}, "Deal Desk AI"),
    prospects: (id, stage) => getj(cid(id) + "/prospects" + (stage ? "?stage=" + encodeURIComponent(stage) : "")),
  };
  // Outreach campaigns. Sending is off in this build: the only transport records what would be sent.
  const oq = (o) => (o ? "?" + new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== "")).toString() : "");
  window.DD_OUTREACH = {
    list: () => getj("/api/outreach/campaign"),
    get: (id) => getj("/api/outreach/campaign?id=" + encodeURIComponent(id)),
    save: (id, plan) => post("/api/outreach/campaign", { id, plan }, "Deal Desk"),
    accounts: (b) => post("/api/outreach/accounts", b, "Deal Desk"),
    authorize: (campaign_id, confirm_scope_hash) => post("/api/outreach/authorize", { campaign_id, confirm_scope_hash }, "Deal Desk"),
    control: (b) => post("/api/outreach/control", b, "Deal Desk"),
    preview: (b) => post("/api/outreach/preview", b, "Deal Desk AI"),
    outbox: (o) => getj("/api/outreach/outbox" + oq(o)),
    log: (o) => getj("/api/outreach/log" + oq(o)),
    suppression: () => getj("/api/outreach/suppression"),
    suppress: (b) => post("/api/outreach/suppression", b, "Deal Desk"),
    reply: (b) => post("/api/outreach/reply", b, "Deal Desk AI"),
    linkedin: (o) => getj("/api/outreach/linkedin" + oq(o)),
    linkedinAct: (b) => post("/api/outreach/linkedin", b, "Deal Desk"),
  };
  window.DD_COVERAGE = (fresh) => getj("/api/panel/coverage" + (fresh ? "?fresh=1" : ""));
  window.DD_GEO = { get: (lang) => getj("/api/panel/brief?kind=geo&lang=" + lang), build: (lang) => post("/api/panel/brief", { lang, kind: "geo" }, "Deal Desk AI") };
  window.DD_BRIEF = { get: (lang) => getj("/api/panel/brief?lang=" + lang), build: (lang) => post("/api/panel/brief", { lang }, "Deal Desk AI") };
  window.DD_KNOW = (names) => post("/api/panel/know", { names }, "Deal Desk");
  window.DD_COUNTRY = (c) => getj("/api/panel/country?c=" + encodeURIComponent(c));
  // one automatic retry when the connection drops (a cold server can drop the first long request)
  window.DD_SUPSEARCH = async (q) => { const b = Object.assign({ research: true }, q); try { return await post("/api/panel/suppliers-for", b, "Deal Desk"); } catch (e) { if (!e || !e.retryable) throw e; await new Promise((r) => setTimeout(r, 1500)); return post("/api/panel/suppliers-for", b, "Deal Desk"); } };
  // Official contact details for one supplier, fetched only when its file is opened.
  window.DD_CONTACT = async (name, country) => (await post("/api/panel/contact", { name, country }, "Deal Desk")).contact || null;

  window.claude = {
    async use(name) {
      if (name === "mcp") return mcp;
      if (name === "sample") {
        if (aiOn === null) aiOn = await fetch("/api/panel/ai", { credentials: "same-origin" }).then((r) => r.json()).then((j) => !!j.enabled).catch(() => false);
        if (aiOn) return sample;
        throw err("server_not_connected", "AI");
      }
      throw err("server_not_connected", name);
    },
  };
})();
