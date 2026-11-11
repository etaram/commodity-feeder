// Where the app reads the engine's data files from. Default: the public GitHub repository (as on Vercel). On our own
// server DATA_BASE_URL points at the data service on the private network (the same tree: /data/..., /dealdesk/public/...),
// so the data no longer has to sit in a public repository. No trailing slash.
// TODO(remove with the public repository): PUBLIC FALLBACK. When DATA_BASE_URL is not set the data is read from the
// public GitHub repository. It must keep working until the repository is private; then delete the fallback URL here and
// in app/route.ts and make a missing DATA_BASE_URL an error. Until then production only logs one warning per instance.
export const PUBLIC_FALLBACK = !process.env.DATA_BASE_URL;
let warned = false;
/** One structured warning per server instance when production still reads from the public repository. Behaviour is unchanged. */
export function warnPublicFallback(where: string) {
  if (warned || !PUBLIC_FALLBACK || process.env.NODE_ENV !== "production") return;
  warned = true;
  console.warn(JSON.stringify({ level: "warn", event: "data_base_url_missing", where, note: "DATA_BASE_URL is not set in production: data is read from the public GitHub repository (fallback marked for removal)" }));
}
warnPublicFallback("lib/rawbase");
export const RAW_ROOT = (process.env.DATA_BASE_URL || "https://raw.githubusercontent.com/etaram/commodity-feeder/main").replace(/\/+$/, "");
