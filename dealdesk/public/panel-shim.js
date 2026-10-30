(() => {
  "use strict";
  const RANGE_KEY = {
    "'My Leads'!A1:AE1500": "tenders", "'Titles HE'!A1:B20000": "titles", "'BD Agent'!A1:M600": "bd",
    "'Key Accounts'!A1:S400": "accounts", "'Repeat Buyers'!A1:O5600": "repeat", "'Market Signals'!A1:O3200": "markets",
    "'Meta'!A1:B5": "meta", "'Intel'!A1:P2000": "intel", "'Upcoming'!A1:AE1500": "upcoming", "'Stats'!A1:B60": "stats",
    "'Pursuits'!A1:V600": "pursuits", "'Panel Jobs'!A1:L800": "jobs", "'Suppliers'!A1:AJ6001": "suppliers",
    "'Grants'!A1:L1500": "grants", "'Exempt Buys'!A1:Q4001": "exempt", "'IL Exemption Contracts'!A1:R3000": "ilex", "'Integrity'!A1:N300": "integrity",
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
    async callTool(server, tool, args) {
      if (server === "Google Sheets") {
        const range = String(args.range || "");
        if (tool === "get_values") {
          if (range.startsWith("'Panel Search'!A9")) {
            const kind = args.spreadsheetId === SU ? "c" : "t";
            const j = await post("/api/panel/search", { kind, values: lastSearch[kind] || [] });
            return { payload: { values: j.values }, cache: { storedAt: Date.now() } };
          }
          const key = range === "'Panel Search'!A6:B6" ? "tot_t" : range === "'Panel Search'!D1:E1" ? "tot_s" : RANGE_KEY[range];
          if (!key) throw err("tool_error", "Google Sheets", "range not available on the web: " + range);
          const j = await post("/api/panel/get", { key });
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
  async function ai(prompt, opts) {
    const j = await post("/api/panel/ai", { prompt, tier: opts && opts.modelTier });
    return j.text || "";
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
