// The key the app uses to call its own routes during the self-check (20 deal scenarios, lib/scenarios.ts). It is derived
// from AUTH_SECRET (the secret that already signs every session), so it adds no new secret, is never stored or sent
// outside the server, and changes when AUTH_SECRET changes. Web Crypto: works in the middleware and in the routes.
let memo: string | null = null;
export async function selfKey(): Promise<string> {
  if (memo !== null) return memo;
  const sec = process.env.AUTH_SECRET || "";
  if (sec.length < 16) return (memo = "");
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(sec), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode("dd-selfcheck-v1"));
  return (memo = Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join(""));
}

// The secret part of the MCP address (app/api/mcp/[key]): derived from AUTH_SECRET like the self-check key, so it adds
// no secret to manage; changing AUTH_SECRET revokes every MCP address at once. Only an admin can read it (/api/mcp/key).
let mcpMemo: string | null = null;
export async function mcpKey(): Promise<string> {
  if (mcpMemo !== null) return mcpMemo;
  const sec = process.env.AUTH_SECRET || "";
  if (sec.length < 16 || process.env.MCP_DISABLED === "1") return (mcpMemo = "");
  const k = await crypto.subtle.importKey("raw", new TextEncoder().encode(sec), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", k, new TextEncoder().encode("dd-mcp-v1"));
  return (mcpMemo = Array.from(new Uint8Array(sig)).map((b) => b.toString(16).padStart(2, "0")).join(""));
}
