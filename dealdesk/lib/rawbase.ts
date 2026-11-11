// Where the app reads the engine's data files from. Default: the public GitHub repository (as on Vercel). On our own
// server DATA_BASE_URL points at the data service on the private network (the same tree: /data/..., /dealdesk/public/...),
// so the data no longer has to sit in a public repository. No trailing slash.
export const RAW_ROOT = (process.env.DATA_BASE_URL || "https://raw.githubusercontent.com/etaram/commodity-feeder/main").replace(/\/+$/, "");
