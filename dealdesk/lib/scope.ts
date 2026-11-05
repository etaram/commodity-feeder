import { DEFAULT_WS } from "@/lib/auth";

// Data scopes (spec section 15): reusable public knowledge, organisation-private information, user-private state.
// The sheet tabs below are the original workspace's private records (its buyers, pursuits, research jobs, contacts,
// projects, intelligence notes and watchlist). Another workspace gets an empty grid for them and cannot write to
// them; public collections (tenders, suppliers, markets, plays, grants) are shared. Deny by default: a new tab is
// private until it is added to PUBLIC_KEYS.
export const PUBLIC_KEYS = new Set(["tenders", "titles", "repeat", "markets", "plays", "fx", "meta", "upcoming", "stats",
  "suppliers", "grants", "exempt", "ilex", "integrity", "tot_t", "tot_s", "websup"]);
export const ownWorkspace = (ws: string) => ws === DEFAULT_WS;
export function canRead(ws: string, key: string): boolean {
  return ownWorkspace(ws) || PUBLIC_KEYS.has(key);
}
export const canWriteOwnerTabs = (ws: string) => ownWorkspace(ws);
