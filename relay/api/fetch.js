// Regional fetch relay: GET /api/fetch?url=https://... with header x-relay-secret.
// Runs in the project's Vercel region (fra1 for sinder-relay-eu) so collectors in GitHub Actions (US) can read
// portals that refuse US addresses. Returns the body base64-encoded with the status and content type.
// Only https, only GET, 25 s timeout, 4 MB cap, optional host allowlist (RELAY_HOSTS). No cookies kept.
export default async function handler(req, res) {
  const secret = process.env.RELAY_SECRET || "";
  if (!secret || req.headers["x-relay-secret"] !== secret) return res.status(401).json({ ok: false, error: "unauthorised" });
  const url = String(req.query.url || "");
  let u;
  try { u = new URL(url); } catch { return res.status(400).json({ ok: false, error: "bad url" }); }
  if (u.protocol !== "https:" && u.protocol !== "http:") return res.status(400).json({ ok: false, error: "https only" });
  const allow = (process.env.RELAY_HOSTS || "").split(",").map((s) => s.trim().toLowerCase()).filter(Boolean);
  if (allow.length && !allow.some((h) => u.hostname === h || u.hostname.endsWith("." + h))) return res.status(403).json({ ok: false, error: "host not allowed" });
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), 25000);
  try {
    const r = await fetch(u.toString(), {
      signal: ctl.signal, redirect: "follow",
      headers: { "user-agent": req.headers["x-relay-ua"] || "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
                 "accept": req.headers["x-relay-accept"] || "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8", "accept-language": "en-US,en;q=0.9" },
    });
    const buf = Buffer.from(await r.arrayBuffer());
    if (buf.length > 4 * 1024 * 1024) return res.status(502).json({ ok: false, error: "body over 4 MB" });
    return res.status(200).json({ ok: true, status: r.status, type: r.headers.get("content-type") || "", url: r.url, body: buf.toString("base64") });
  } catch (e) {
    return res.status(502).json({ ok: false, error: String(e && e.name === "AbortError" ? "timeout" : e).slice(0, 200) });
  } finally { clearTimeout(t); }
}
