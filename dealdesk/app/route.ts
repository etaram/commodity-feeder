// "/" is the Opportunity Panel: the same page as the panel inside Claude, loaded from the repo (dealdesk/public/panel.html)
// so panel updates do not need a redeploy. The page talks to this server through /panel-shim.js.
export const dynamic = "force-dynamic";
// Preview deployments (VERCEL_ENV=preview) read the "staging" branch so a change can be tried before it goes live.
const REF = process.env.VERCEL_ENV === "preview" ? "staging" : "main";
const SRC = `https://raw.githubusercontent.com/etaram/commodity-feeder/${REF}/dealdesk/public/panel.html`;
let hit: { at: number; html: string } | null = null;

export async function GET() {
  if (!hit || Date.now() - hit.at > 300_000) {
    const r = await fetch(SRC, { cache: "no-store" }).catch(() => null);
    if (r && r.ok) hit = { at: Date.now(), html: await r.text() };
  }
  if (!hit) return new Response("The panel could not be loaded, try again in a minute. Classic screens: /today", { status: 503 });
  return new Response(hit.html, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
}
